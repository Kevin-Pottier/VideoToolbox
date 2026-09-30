import math
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Tuple

from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button
from audio_tracks import ffprobe_streams

# Real-ESRGAN is not stored in the repository: `python scripts/fetch_deps.py` downloads it into Tool/
TOOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Tool")
REALESRGAN_EXE = os.path.join(TOOL_DIR, "realesrgan-ncnn-vulkan.exe" if sys.platform == "win32" else "realesrgan-ncnn-vulkan")
MODEL_NAME = "realesrgan-x4plus"
# realesrgan-x4plus is a x4 network: with "-s 2" the binary outputs a garbled crop.
# It is always run at x4, then ffmpeg resizes the result to the requested height.
MODEL_SCALE = 4
# Approximate size of a high quality JPEG frame, used to estimate the temporary disk space
JPEG_BYTES_PER_PIXEL = 0.5


class UpscaleError(Exception):
    pass


class UpscaleCancelled(Exception):
    pass


def _rate_to_float(rate):
    """Convert an ffprobe rational ('24000/1001') to a float, 0.0 if invalid."""
    try:
        num, _, den = rate.partition("/")
        return float(num) / float(den or 1)
    except (AttributeError, ValueError, ZeroDivisionError):
        return 0.0


def probe_video(filepath):
    """
    Read the properties of the first video stream with ffprobe.
    Returns:
        dict or None: width, height, fps (ffmpeg rational string) and duration (s).
    """
    try:
        media = ffprobe_streams(filepath)
    except RuntimeError as e:
        print(f"Could not read {filepath}: {e}")
        return None
    if not media.video_tracks:
        return None
    video = media.video_tracks[0]  # the stream extracted with -map 0:v:0
    duration = media.duration or 0
    # The same rate is used to extract and to recompose the frames,
    # so the output keeps the source duration and the audio stays in sync.
    fps = next((r for r in (video.avg_frame_rate, video.r_frame_rate) if _rate_to_float(r) > 0), None)
    if not video.width or not video.height or fps is None or duration <= 0:
        return None
    return {"width": video.width, "height": video.height, "fps": fps, "duration": duration}


def estimate_frame_count(info):
    return int(math.ceil(info["duration"] * _rate_to_float(info["fps"])))


def estimate_temp_space(info):
    """Rough size in bytes of the extracted and upscaled frames of one video."""
    pixels = info["width"] * info["height"]
    return int(estimate_frame_count(info) * pixels * (1 + MODEL_SCALE ** 2) * JPEG_BYTES_PER_PIXEL)


def _format_duration(seconds):
    hours, rem = divmod(int(seconds), 3600)
    mins, secs = divmod(rem, 60)
    return f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"


def _log_tail(log_path, lines=12):
    """Last meaningful lines of a log file (Real-ESRGAN progress lines are skipped)."""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            content = [l.rstrip() for l in f if l.strip() and not l.strip().endswith("%")]
    except OSError:
        return ""
    return "\n".join(content[-lines:])


def upscale_resolution_choices(width, height):
    """Returns a list of tuples (label, target height) for resolutions higher than the source."""
    resolutions = [
        ("720p (1280x720)", 720),
        ("1080p (1920x1080)", 1080),
        ("4K (3840x2160)", 2160),
    ]
    return [(label, h) for label, h in resolutions if h > height]


def _run_ffmpeg(args, log_path, report, cancel_event, step):
    """Run ffmpeg, report the frame counter and raise UpscaleError/UpscaleCancelled."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"] + args
    print("  " + " ".join(cmd))
    # stderr goes to a file: a pipe that is not read would block ffmpeg once full
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, universal_newlines=True)
        for line in proc.stdout:
            if cancel_event.is_set():
                proc.terminate()
                proc.wait()
                raise UpscaleCancelled()
            if line.startswith("frame="):
                try:
                    report("progress", int(line[len("frame="):]))
                except ValueError:
                    pass
        proc.wait()
    if proc.returncode != 0:
        raise UpscaleError(f"{step} failed:\n{_log_tail(log_path)}")


def upscale_video(filepath, info, target_height, outdir, report, cancel_event):
    """
    Upscale one video: extract the frames, upscale them with Real-ESRGAN, recompose the video.
    Runs in a worker thread: it never touches Tk and only sends messages through report(kind, *args).
    Returns:
        str: path of the upscaled video.
    Raises:
        UpscaleError, UpscaleCancelled
    """
    video_name, src_ext = os.path.splitext(os.path.basename(filepath))
    # MP4 sources carry MP4-compatible audio; anything else goes to MKV so that "-c:a copy" always works
    out_ext = ".mp4" if src_ext.lower() == ".mp4" else ".mkv"
    output_video = os.path.join(outdir, f"{video_name}_upscaled_{target_height}p{out_ext}")
    work_dir = tempfile.mkdtemp(prefix=f".upscale_{video_name}_", dir=outdir)
    frames_dir = os.path.join(work_dir, "frames")
    frames_up_dir = os.path.join(work_dir, "frames_upscaled")
    log_path = os.path.join(work_dir, "log.txt")
    os.makedirs(frames_dir)
    os.makedirs(frames_up_dir)
    try:
        # 1. Extract frames at a constant rate, with square pixels (anamorphic sources such as DVDs)
        report("stage", "Extracting frames", estimate_frame_count(info))
        _run_ffmpeg([
            "-i", filepath, "-map", "0:v:0",
            "-vf", f"fps={info['fps']},scale=trunc(iw*sar/2)*2:ih,setsar=1",
            "-q:v", "2", os.path.join(frames_dir, "frame_%08d.jpg")
        ], log_path, report, cancel_event, "Frame extraction")
        n_frames = len(os.listdir(frames_dir))
        if n_frames == 0:
            raise UpscaleError("Frame extraction failed: no frame extracted.")

        # 2. Upscale the frames (output files keep the input names)
        report("stage", f"Upscaling frames (Real-ESRGAN x{MODEL_SCALE})", n_frames)
        up_cmd = [
            REALESRGAN_EXE,
            "-i", frames_dir,
            "-o", frames_up_dir,
            "-n", MODEL_NAME,
            "-s", str(MODEL_SCALE),
            "-f", "jpg",
            "-m", os.path.join(TOOL_DIR, "models"),
        ]
        print("  " + " ".join(up_cmd))
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.Popen(up_cmd, stdout=log, stderr=subprocess.STDOUT)
            while proc.poll() is None:
                if cancel_event.is_set():
                    proc.terminate()
                    proc.wait()
                    raise UpscaleCancelled()
                report("progress", len(os.listdir(frames_up_dir)))
                time.sleep(1)
        n_upscaled = len(os.listdir(frames_up_dir))
        if proc.returncode != 0 or n_upscaled != n_frames:
            raise UpscaleError(
                f"Real-ESRGAN failed ({n_upscaled}/{n_frames} frames upscaled, exit code {proc.returncode}):\n"
                f"{_log_tail(log_path)}"
            )
        shutil.rmtree(frames_dir, ignore_errors=True)  # free disk space before recomposing

        # 3. Recompose at the extraction rate, resize to the target height, copy the audio (if any)
        report("stage", "Recomposing video", n_frames)
        try:
            _run_ffmpeg([
                "-framerate", info["fps"], "-i", os.path.join(frames_up_dir, "frame_%08d.jpg"),
                "-i", filepath,
                "-map", "0:v", "-map", "1:a?",
                "-vf", f"scale=-2:{target_height}:flags=lanczos",
                "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-y", output_video
            ], log_path, report, cancel_event, "Recomposition")
        except (UpscaleError, UpscaleCancelled):
            if os.path.exists(output_video):
                os.remove(output_video)
            raise
        return output_video
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_upscale_jobs(root, jobs, outdir):
    """
    Upscale the videos one after another in a worker thread while a progress window is shown.
    Closing the window cancels the remaining work.
    Args:
        jobs (list): (filepath, info from probe_video, target height) tuples.
    Returns:
        list: (filename, success, output path or error message) tuples.
    """
    messages = queue.Queue()
    cancel_event = threading.Event()
    results = []

    win = tk.Toplevel(root)
    win.title("Video Upscaling")
    win.configure(bg="#23272e")
    apply_modern_theme(win)
    frame = create_styled_frame(win)
    frame.pack(fill="both", expand=True, padx=14, pady=14)
    file_label = create_styled_label(frame, "", style='Title.TLabel')
    file_label.pack(pady=(0, 6))
    stage_label = create_styled_label(frame, "Starting...")
    stage_label.pack()
    progress_var = tk.DoubleVar(master=win)
    progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=1, length=380)
    progress_bar.pack(pady=8)
    eta_label = create_styled_label(frame, "Time left: --:--", font=("Segoe UI", 10, "italic"))
    eta_label.pack()
    stage = {"total": 1, "start": time.time()}

    def worker():
        report = messages.put_nowait
        try:
            for index, (filepath, info, target_height) in enumerate(jobs, 1):
                name = os.path.basename(filepath)
                if cancel_event.is_set():
                    report(("result", name, False, "Cancelled."))
                    continue
                report(("job", index, len(jobs), name))
                try:
                    output = upscale_video(filepath, info, target_height, outdir, lambda *msg: report(msg), cancel_event)
                    report(("result", name, True, output))
                except UpscaleCancelled:
                    report(("result", name, False, "Cancelled."))
                except Exception as e:  # report the error and go on with the next video
                    report(("result", name, False, str(e) or type(e).__name__))
        finally:
            # Always sent, otherwise the progress window would never close
            report(("finished",))

    def poll():
        try:
            while True:
                msg = messages.get_nowait()
                kind = msg[0]
                if kind == "job":
                    file_label.config(text=f"({msg[1]}/{msg[2]}) {msg[3]}")
                    print(f"[{msg[3]}] Upscaling...")
                elif kind == "stage":
                    stage["total"], stage["start"] = max(msg[2], 1), time.time()
                    stage_label.config(text=msg[1])
                    progress_bar.config(maximum=stage["total"])
                    progress_var.set(0)
                    eta_label.config(text="Time left: --:--")
                elif kind == "progress":
                    done = min(msg[1], stage["total"])
                    progress_var.set(done)
                    if done > 0:
                        remaining = (time.time() - stage["start"]) / done * (stage["total"] - done)
                        eta_label.config(text=f"Time left: {_format_duration(remaining)}")
                elif kind == "result":
                    name, ok, detail = msg[1:]
                    results.append((name, ok, detail))
                    print(f"[{name}] " + (f"Upscaled video saved to {detail}" if ok else f"FAILED: {detail}"))
                elif kind == "finished":
                    win.destroy()
                    return
        except queue.Empty:
            pass
        win.after(200, poll)

    def on_close():
        if messagebox.askyesno("Cancel", "Stop the upscaling in progress?", parent=win):
            cancel_event.set()
            stage_label.config(text="Cancelling...")

    win.protocol("WM_DELETE_WINDOW", on_close)
    threading.Thread(target=worker, daemon=True).start()
    poll()
    win.wait_window()
    return results


def _ask_target_height(root, filename, width, height, choices):
    """Dialog to choose the target resolution of one video. Returns the height, or None if cancelled."""
    win = tk.Toplevel(root)
    win.title(f"Upscale - {filename}")
    win.configure(bg="#23272e")
    apply_modern_theme(win)
    frame = create_styled_frame(win)
    frame.pack(fill="both", expand=True, padx=14, pady=10)
    create_styled_label(frame, filename, style='Title.TLabel').pack(pady=(2, 2))
    create_styled_label(frame, f"Original resolution: {width}x{height}").pack(pady=(0, 10))
    selected = {"height": None}

    def choose(h):
        selected["height"] = h
        win.destroy()

    for label, h in choices:
        create_styled_button(frame, label, lambda h=h: choose(h), width=20).pack(pady=4)
    create_styled_button(frame, "Cancel", win.destroy, width=20).pack(pady=(12, 4))
    win.lift()
    win.wait_window()
    return selected["height"]


def run_video_upscale_gui():
    root = tk.Tk()
    root.withdraw()
    try:
        _run_video_upscale(root)
    finally:
        root.destroy()


def _run_video_upscale(root):
    if not os.path.isfile(REALESRGAN_EXE):
        messagebox.showerror(
            "Real-ESRGAN not installed",
            f"{os.path.basename(REALESRGAN_EXE)} was not found in:\n{TOOL_DIR}\n\n"
            "Download it with:\n    python scripts/fetch_deps.py",
            parent=root
        )
        return
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        messagebox.showerror("FFmpeg not found", f"{' and '.join(missing)} must be installed and in the PATH.", parent=root)
        return

    # Video selection
    filepaths = filedialog.askopenfilenames(
        parent=root,
        title="Select one or more videos to upscale",
        filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm")]
    )
    if not filepaths:
        print("No video selected.")
        return

    # For each video, detect resolution and ask for target
    jobs: List[Tuple[str, dict, int]] = []
    for filepath in filepaths:
        filename = os.path.basename(filepath)
        info = probe_video(filepath)
        if info is None:
            messagebox.showerror("Error", f"Could not read the video properties of {filename}.", parent=root)
            continue
        choices = upscale_resolution_choices(info["width"], info["height"])
        if not choices:
            messagebox.showinfo("Info", f"{filename} ({info['width']}x{info['height']}): no higher resolution available.", parent=root)
            continue
        target_height = _ask_target_height(root, filename, info["width"], info["height"], choices)
        if target_height is None:
            print(f"Upscale cancelled for {filename}.")
            continue
        jobs.append((filepath, info, target_height))
    if not jobs:
        print("No video to upscale.")
        return

    # Output folder selection
    outdir = filedialog.askdirectory(parent=root, title="Choose output folder for upscaled videos")
    if not outdir:
        print("No output folder selected.")
        return

    # Temporary frames are deleted after each video: the peak usage is the largest video
    needed = max(estimate_temp_space(info) for _, info, _ in jobs)
    free = shutil.disk_usage(outdir).free
    print(f"Estimated temporary disk space: {needed / 1e9:.1f} GB (free: {free / 1e9:.1f} GB)")
    if needed > free and not messagebox.askyesno(
            "Not enough disk space?",
            f"Upscaling needs roughly {needed / 1e9:.0f} GB of temporary frames, "
            f"but only {free / 1e9:.0f} GB are free in:\n{outdir}\n\nContinue anyway?",
            icon="warning", parent=root):
        return

    print("--- Upscale jobs to perform ---")
    for filepath, info, target_height in jobs:
        print(f"  {os.path.basename(filepath)}: {info['width']}x{info['height']} -> {target_height}p")
    results = run_upscale_jobs(root, jobs, outdir)

    succeeded = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    lines = [f"{len(succeeded)}/{len(results)} video(s) upscaled."]
    lines += [f"✔ {os.path.basename(detail)}" for _, _, detail in succeeded]
    lines += [f"✘ {name}: {detail.splitlines()[0]}" for name, _, detail in failed]
    if failed:
        lines.append("\nSee console for details.")
        messagebox.showwarning("Upscaling finished", "\n".join(lines), parent=root)
    else:
        messagebox.showinfo("Upscaling finished", "\n".join(lines), parent=root)
