import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import List, Tuple

import encoders
from gui_helpers import apply_modern_theme, choose_encoder, create_styled_frame, create_styled_label, create_styled_button
from audio_tracks import ffprobe_streams

# Real-ESRGAN is not stored in the repository: `python scripts/fetch_deps.py` downloads it into Tool/
TOOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Tool")
REALESRGAN_EXE = os.path.join(TOOL_DIR, "realesrgan-ncnn-vulkan.exe" if sys.platform == "win32" else "realesrgan-ncnn-vulkan")


@dataclass(frozen=True)
class Model:
    name: str        # Real-ESRGAN model name (-n)
    scales: tuple    # native scales of the network: other values give wrong images
    label: str


MODELS = [
    Model("realesrgan-x4plus", (4,), "Live action: realesrgan-x4plus (best quality, slow)"),
    Model("realesr-animevideov3", (2, 3, 4), "Animation: realesr-animevideov3 (about 10 times faster)"),
]
# Approximate size of a high quality JPEG frame and of a PNG frame, used for the disk space and the chunks
JPEG_BYTES_PER_PIXEL = 0.5
PNG_BYTES_PER_PIXEL = 2.0
# Upscaled frames written per chunk (about): only a few chunks are on the disk at the same time
CHUNK_BYTES = 1_000_000_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Real-ESRGAN prints the progress of a frame ("25.00%") when it starts each of its tiles
TILE_PROGRESS = re.compile(r"^(\d+(?:\.\d+)?)%$", re.MULTILINE)


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


def model_scale(model, source_height, target_height):
    """Smallest native scale of the model that reaches the target height (ffmpeg resizes the rest)."""
    ratio = target_height / source_height
    return next((scale for scale in model.scales if scale >= ratio), model.scales[-1])


def chunk_frames(width, height, scale):
    """Number of frames per chunk, so that a chunk of upscaled frames weighs about CHUNK_BYTES."""
    upscaled_frame = width * height * scale * scale * JPEG_BYTES_PER_PIXEL
    return max(8, min(1000, int(CHUNK_BYTES / upscaled_frame)))


def estimate_temp_space(info, scale=4):
    """
    Peak size in bytes of the temporary frames: the frames go through the pipeline in chunks,
    at most two chunks of decoded frames and three chunks of upscaled frames exist at once.
    """
    pixels = info["width"] * info["height"]
    frames = min(chunk_frames(info["width"], info["height"], scale), estimate_frame_count(info))
    return int(frames * pixels * (2 * PNG_BYTES_PER_PIXEL + 3 * scale * scale * JPEG_BYTES_PER_PIXEL))


def _format_size(size):
    """Bytes as a short readable size: "750 MB", "3.5 GB"."""
    return f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{max(size, 1e6) / 1e6:.0f} MB"


def confirm_temp_space(root, needed, free, outdir):
    """
    Tell how much temporary disk space the upscaling needs, and let the user decide whether to start.
    When the folder has not enough free space, the question is a warning and "No" is the default answer.
    Returns True to start the upscaling.
    """
    enough = needed <= free
    message = (f"The upscaling needs about {_format_size(needed)} of temporary disk space (frames deleted at the "
               f"end), plus the upscaled videos, in:\n{outdir}\n\nFree space: {_format_size(free)}.")
    if not enough:
        message += "\n\n⚠ This is not enough: the upscaling will probably fail when the disk is full."
    return messagebox.askyesno("Temporary disk space" if enough else "Not enough disk space",
                               message + "\n\nStart the upscaling?", icon="question" if enough else "warning",
                               default="yes" if enough else "no", parent=root)


def _format_duration(seconds):
    hours, rem = divmod(int(seconds), 3600)
    mins, secs = divmod(rem, 60)
    if hours >= 48:
        return f"{hours // 24} days {hours % 24} h"
    return f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"


def _speed_text(seconds_per_frame):
    if seconds_per_frame < 1:
        return f"{1 / seconds_per_frame:.1f} frames/s"
    return f"{_format_duration(seconds_per_frame)} per frame" if seconds_per_frame >= 60 else f"{seconds_per_frame:.0f} s per frame"


def frames_done(log_text, finished):
    """
    Frames upscaled, fractions included, from the log of Real-ESRGAN and the number of finished frames.
    Real-ESRGAN prints the progress of a frame when it starts each of its tiles ("0.00%", "25.00%", "50.00%",
    "75.00%" for 4 tiles; frames processed at the same time are interleaved): every line but the last one
    of each frame in progress is a finished tile. This measures the progress inside frames that take
    minutes (a large frame upscaled x4 on a modest GPU), so that the time left does not wait for them.
    """
    values = [float(value) for value in TILE_PROGRESS.findall(log_text)]
    steps = [value for value in values if value > 0]
    if not steps:  # the size of the tiles is not known before the first tile is finished
        return finished
    tiles_per_frame = round(100 / min(steps))
    in_progress = max(values.count(0.0) - finished, 0)  # each frame starts with "0.00%"
    return max(finished, (len(values) - in_progress) / tiles_per_frame)


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


def _read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise UpscaleError("The decoded frames ended in the middle of an image.")
    return data


def read_png_frames(stream):
    """Split a stream of concatenated PNG images (ffmpeg -f image2pipe -c:v png) into images."""
    while True:
        signature = stream.read(len(PNG_SIGNATURE))
        if not signature:
            return
        if signature != PNG_SIGNATURE:
            raise UpscaleError("Unexpected data in the decoded frames.")
        parts = [signature]
        while True:  # PNG chunks: length, type, data, CRC; the image ends with the IEND chunk
            header = _read_exact(stream, 8)
            parts += [header, _read_exact(stream, int.from_bytes(header[:4], "big") + 4)]
            if header[4:] == b"IEND":
                break
        yield b"".join(parts)


def upscale_video(filepath, info, target_height, outdir, report, cancel_event, model=MODELS[0], encoder=None):
    """
    Upscale one video with Real-ESRGAN. Three stages run at the same time, linked by pipes and queues:
    ffmpeg decodes the frames (PNG, lossless) into chunks of files, Real-ESRGAN upscales one chunk while
    the next one is decoded, and a second ffmpeg encodes the upscaled frames as they come. The total time
    is close to the time of the slowest stage, and only a few chunks are on the disk at once.
    Runs in a worker thread: it never touches Tk and only sends messages through report(kind, *args).
    Returns:
        str: path of the upscaled video.
    Raises:
        UpscaleError, UpscaleCancelled
    """
    encoder = encoder or encoders.DEFAULT
    scale = model_scale(model, info["height"], target_height)
    fps = info["fps"]
    frames_per_chunk = chunk_frames(info["width"], info["height"], scale)
    video_name, src_ext = os.path.splitext(os.path.basename(filepath))
    # MP4 sources carry MP4-compatible audio; anything else goes to MKV so that "-c:a copy" always works
    out_ext = ".mp4" if src_ext.lower() == ".mp4" else ".mkv"
    output_video = os.path.join(outdir, f"{video_name}_upscaled_{target_height}p{out_ext}")
    work_dir = tempfile.mkdtemp(prefix=f".upscale_{video_name}_", dir=outdir)
    logs = {name: os.path.join(work_dir, f"{name}.log") for name in ("decode", "upscale", "encode")}
    to_upscale = queue.Queue(maxsize=1)  # chunks of decoded frames waiting for Real-ESRGAN
    to_encode = queue.Queue(maxsize=1)   # chunks of upscaled frames waiting for the encoder
    stop = threading.Event()
    errors = []
    processes = []
    counts = {"decoded": 0, "upscaled": 0, "encoded": 0}

    def fail(error):
        errors.append(error)
        stop.set()

    def put(q, item):
        while not stop.is_set() and not cancel_event.is_set():
            try:
                q.put(item, timeout=0.5)
                return
            except queue.Full:
                pass

    def get(q):
        while not stop.is_set() and not cancel_event.is_set():
            try:
                return q.get(timeout=0.5)
            except queue.Empty:
                pass
        return None

    def start(cmd, log_name, **kwargs):
        print("  " + " ".join(cmd))
        log = open(logs[log_name], "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(cmd, stderr=log, **kwargs)
        log.close()  # the process keeps its own handle
        processes.append(proc)
        return proc

    def shutdown():
        """Kill the processes: a stage thread blocked on one of them (e.g. on a full pipe) can then finish."""
        stop.set()
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
            proc.wait()

    # The pipes apply back-pressure: the decoder waits while its chunks are not consumed.
    # Decoder: constant rate, square pixels (anamorphic sources such as DVDs), lossless PNG frames on stdout
    decode_cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", filepath, "-map", "0:v:0",
                  "-vf", f"fps={fps},scale=trunc(iw*sar/2)*2:ih,setsar=1",
                  "-f", "image2pipe", "-c:v", "png", "-compression_level", "1", "-"]
    # Encoder: upscaled frames on stdin, resized to the target height, audio copied
    out_width = int(target_height * 16 / 9)  # only used for the bitrate of GPU encoders
    encode_cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", *encoders.input_args(encoder),
                  "-f", "image2pipe", "-framerate", fps, "-c:v", "mjpeg", "-i", "-",
                  "-i", filepath, "-map", "0:v", "-map", "1:a?",
                  *encoders.filter_args(encoder, [f"scale=-2:{target_height}:flags=lanczos"]),
                  *encoders.quality_args(encoder, out_width, target_height, _rate_to_float(fps)),
                  "-c:a", "copy", output_video]
    decoder = encoder_proc = None

    def decode_chunks():
        try:
            frames = read_png_frames(decoder.stdout)
            chunk = 0
            while not stop.is_set() and not cancel_event.is_set():
                chunk_dir = os.path.join(work_dir, f"in_{chunk:06d}")
                os.makedirs(chunk_dir)
                count = 0
                for data in frames:
                    counts["decoded"] += 1
                    with open(os.path.join(chunk_dir, f"frame_{counts['decoded']:08d}.png"), "wb") as f:
                        f.write(data)
                    count += 1
                    if count == frames_per_chunk:
                        break
                if count:
                    put(to_upscale, chunk_dir)
                else:
                    os.rmdir(chunk_dir)
                if count < frames_per_chunk:
                    break
                chunk += 1
            if decoder.wait() != 0 and not stop.is_set() and not cancel_event.is_set():
                raise UpscaleError(f"Frame decoding failed:\n{_log_tail(logs['decode'])}")
        except Exception as e:
            fail(e)
        finally:
            put(to_upscale, None)

    def encode_chunks():
        try:
            while True:
                chunk_dir = get(to_encode)
                if chunk_dir is None:
                    break
                for name in sorted(os.listdir(chunk_dir)):
                    path = os.path.join(chunk_dir, name)
                    with open(path, "rb") as f:
                        encoder_proc.stdin.write(f.read())
                    os.remove(path)
                    counts["encoded"] += 1
                os.rmdir(chunk_dir)
            encoder_proc.stdin.close()
            if encoder_proc.wait() != 0 and not stop.is_set() and not cancel_event.is_set():
                raise UpscaleError(f"Encoding failed:\n{_log_tail(logs['encode'])}")
        except OSError as e:  # the encoder stopped: its log tells why
            if not stop.is_set() and not cancel_event.is_set():
                fail(UpscaleError(f"Encoding failed ({e}):\n{_log_tail(logs['encode'])}"))
        except Exception as e:
            fail(e)

    threads = [threading.Thread(target=decode_chunks, daemon=True), threading.Thread(target=encode_chunks, daemon=True)]
    try:
        report("stage", f"Upscaling x{scale} with {model.name}, encoding with {encoder.name}", estimate_frame_count(info))
        decoder = start(decode_cmd, "decode", stdout=subprocess.PIPE)
        encoder_proc = start(encode_cmd, "encode", stdin=subprocess.PIPE)
        for thread in threads:
            thread.start()
        # 2. Upscale the chunks one after the other (the GPU is the bottleneck)
        while True:
            chunk_dir = get(to_upscale)
            if chunk_dir is None:
                break
            up_dir = chunk_dir.replace("in_", "up_")
            os.makedirs(up_dir)
            n_frames = len(os.listdir(chunk_dir))
            proc = start([REALESRGAN_EXE, "-i", chunk_dir, "-o", up_dir, "-n", model.name, "-s", str(scale),
                          "-f", "jpg", "-m", os.path.join(TOOL_DIR, "models")], "upscale", stdout=subprocess.DEVNULL)
            while proc.poll() is None:
                if stop.is_set() or cancel_event.is_set():
                    break
                # Finished frames, and the finished tiles of the frames in progress
                with open(logs["upscale"], encoding="utf-8", errors="replace") as log:
                    done = frames_done(log.read(), len(os.listdir(up_dir)))
                report("progress", counts["upscaled"] + min(done, n_frames))
                time.sleep(1)
            if stop.is_set() or cancel_event.is_set():
                break
            upscaled = len(os.listdir(up_dir))
            if proc.returncode != 0 or upscaled != n_frames:
                fail(UpscaleError(f"Real-ESRGAN failed ({upscaled}/{n_frames} frames upscaled, exit code "
                                  f"{proc.returncode}):\n{_log_tail(logs['upscale'])}"))
                break
            shutil.rmtree(chunk_dir, ignore_errors=True)
            counts["upscaled"] += n_frames
            report("progress", counts["upscaled"])
            put(to_encode, up_dir)
        if stop.is_set() or cancel_event.is_set():
            shutdown()  # the stage threads may be waiting on a process
        else:
            put(to_encode, None)
        for thread in threads:
            thread.join()
        if cancel_event.is_set():
            raise UpscaleCancelled()
        if errors:
            raise errors[0]
        if not counts["decoded"]:
            raise UpscaleError(f"No frame decoded:\n{_log_tail(logs['decode'])}")
        if counts["encoded"] != counts["decoded"]:
            raise UpscaleError(f"{counts['encoded']}/{counts['decoded']} frames encoded.")
        return output_video
    except BaseException:
        shutdown()  # before removing the output: Windows cannot delete a file the encoder still has open
        if os.path.exists(output_video):
            os.remove(output_video)
        raise
    finally:
        shutdown()
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=5)
        shutil.rmtree(work_dir, ignore_errors=True)


def run_upscale_jobs(root, jobs, outdir, model=MODELS[0], encoder=None):
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
                    output = upscale_video(filepath, info, target_height, outdir, lambda *msg: report(msg), cancel_event,
                                           model, encoder)
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
                    stage.pop("first", None)
                    stage_label.config(text=msg[1])
                    progress_bar.config(maximum=stage["total"])
                    progress_var.set(0)
                    eta_label.config(text="Time left: --:--")
                elif kind == "progress":
                    done = min(msg[1], stage["total"])
                    progress_var.set(done)
                    if done > 0:
                        # Speed measured from the first finished work: the start (model loading) does not count
                        first_time, first_done = stage.setdefault("first", (time.time(), done))
                        if done > first_done:
                            per_frame = (time.time() - first_time) / (done - first_done)
                        else:
                            per_frame = (time.time() - stage["start"]) / done
                        eta_label.config(text=f"Time left: {_format_duration(per_frame * (stage['total'] - done))}"
                                              f"\nframe {int(done) + 1}/{stage['total']}, {_speed_text(per_frame)}")
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


def _ask_model(root):
    """Dialog to choose the Real-ESRGAN model. Returns the Model, or None if cancelled."""
    win = tk.Toplevel(root)
    win.title("Upscale - model")
    win.configure(bg="#23272e")
    apply_modern_theme(win)
    frame = create_styled_frame(win)
    frame.pack(fill="both", expand=True, padx=14, pady=10)
    create_styled_label(frame, "What kind of video?", style='Title.TLabel').pack(anchor="w", pady=(2, 6))
    choice = tk.StringVar(master=win, value=MODELS[0].name)
    for model in MODELS:
        ttk.Radiobutton(frame, text=model.label, variable=choice, value=model.name, style='TRadiobutton').pack(anchor="w", pady=1)
    selected = {}

    def ok():
        selected["model"] = next(m for m in MODELS if m.name == choice.get())
        win.destroy()

    create_styled_button(frame, "OK", ok, width=12).pack(pady=(10, 4))
    win.lift()
    win.wait_window()
    return selected.get("model")


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

    # Model and encoder of the upscaled videos
    model = _ask_model(root)
    if model is None:
        print("No model selected.")
        return
    encoder = choose_encoder("Encoder of the upscaled videos")
    if encoder is None:
        print("No encoder selected.")
        return

    # Output folder selection
    outdir = filedialog.askdirectory(parent=root, title="Choose output folder for upscaled videos")
    if not outdir:
        print("No output folder selected.")
        return

    # The frames go through the pipeline in chunks: the peak usage is a few chunks of the largest video
    needed = max(estimate_temp_space(info, model_scale(model, info["height"], target_height))
                 for _, info, target_height in jobs)
    free = shutil.disk_usage(outdir).free
    print(f"Estimated temporary disk space: {_format_size(needed)} (free: {_format_size(free)})")
    if not confirm_temp_space(root, needed, free, outdir):
        print("Upscaling cancelled.")
        return

    print(f"--- Upscale jobs to perform ({model.name}, {encoder.label}) ---")
    for filepath, info, target_height in jobs:
        print(f"  {os.path.basename(filepath)}: {info['width']}x{info['height']} -> {target_height}p")
    results = run_upscale_jobs(root, jobs, outdir, model, encoder)

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
