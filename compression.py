
import collections
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
from colorama import Fore, Style
from audio_tracks import ffprobe_streams
from utils import fps_mode_option, prepare_subtitle_file
import subprocess
# Import reusable GUI helpers for modern, DRY window/dialog creation
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label

AUDIO_BITRATE = 192000  # bps per audio track: used in the ffmpeg command and in the size budget
SIZE_MARGIN = 0.02  # share of the target size kept for the container overhead and the encoder deviation
MIN_VIDEO_BITRATE_KBPS = 100
FIRST_PASS_SHARE = 0.35  # the analysis pass is faster (x264 uses a fast first pass): share of the progress bar
STALL_TIMEOUT = 300  # seconds without any ffmpeg output after which ffmpeg is considered stuck and killed

def compute_video_bitrate_kbps(max_size_gb, duration, n_audio_tracks):
    """
    Video bitrate (kbps) that makes the output fit in max_size_gb, given the audio
    tracks encoded at AUDIO_BITRATE and the SIZE_MARGIN. Can be negative if the size is too small.
    """
    target_bits = max_size_gb * 1024 * 1024 * 1024 * 8 * (1 - SIZE_MARGIN)  # in bits
    audio_bits_total = AUDIO_BITRATE * n_audio_tracks * duration  # in bits
    video_bitrate = (target_bits - audio_bits_total) / duration  # in bits per second
    return int(video_bitrate / 1000)  # in kbps

def run_compression(file_path, sub_option, sub_file, ext, max_size_gb, gui_progress=None) -> None:
    """
    Compress a video file using FFmpeg, with optional subtitle handling and GUI/CLI progress bars.
    Args:
        file_path (str): Path to the video file.
        sub_option (str): Subtitle option ('none', 'soft', 'hard').
        sub_file (str): Path to the subtitle file (if any).
        ext (str): Output file extension ('mp4' or 'mkv').
        max_size_gb (float): Target maximum file size in GB.
    """
    # Metadata extraction (a single ffprobe call)
    try:
        media = ffprobe_streams(file_path)
    except RuntimeError as e:
        print(Fore.RED + f"Could not read {file_path}: {e}. Aborting." + Style.RESET_ALL)
        return
    duration = media.duration
    if not duration or duration <= 0:
        print(Fore.RED + "Could not determine video duration. Aborting." + Style.RESET_ALL)
        return

    # The audio is re-encoded at AUDIO_BITRATE: the budget depends on the number of output tracks,
    # not on the source bitrate
    n_audio_source = len(media.audio_tracks)
    # 'soft' keeps every audio track (-map 0:a?), otherwise ffmpeg selects a single one
    n_audio_out = n_audio_source if sub_option == "soft" else min(n_audio_source, 1)

    print(f"Duration: {duration:.2f} s")
    print(f"Audio: {n_audio_out} track(s) encoded at {AUDIO_BITRATE // 1000} kbps")

    video_bitrate_kbps = compute_video_bitrate_kbps(max_size_gb, duration, n_audio_out)

    print(f"Target Video Bitrate: {video_bitrate_kbps} kbps")
    if video_bitrate_kbps < MIN_VIDEO_BITRATE_KBPS:
        print(Fore.RED + f"Target size too small: only {video_bitrate_kbps} kbps left for the video "
              f"(minimum {MIN_VIDEO_BITRATE_KBPS} kbps). Aborting." + Style.RESET_ALL)
        return

    output_file = os.path.splitext(file_path)[0] + f"_compressed.{ext}"

    video_name = os.path.basename(file_path)
    input_path = os.path.abspath(file_path)
    output_path = os.path.abspath(output_file)
    # Temporary folder used as ffmpeg working directory: it holds the statistics of the first pass
    # and the subtitle file, copied as UTF-8 under a plain name (any location, name or encoding works)
    work_dir = tempfile.mkdtemp(prefix="videotoolbox_")
    try:
        sub_path = prepare_subtitle_file(sub_file, work_dir) if sub_option in ("soft", "hard") and sub_file else None
    except OSError as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        print(Fore.RED + f"Cannot read the subtitle file {sub_file}: {e}. Aborting." + Style.RESET_ALL)
        return
    try:
        passes = build_two_pass_commands(input_path, output_path, ext, video_bitrate_kbps, sub_option, sub_path, work_dir,
                                         fps_mode_option())
        print(Fore.YELLOW + f"\nRunning ffmpeg (2 passes) with subtitles option: {sub_option}\n" + Style.RESET_ALL)
        for step, (cmd, _) in enumerate(passes, 1):
            print(f"\tPass {step}:", " ".join(cmd))
        print()
        if gui_progress is None:
            ok = _encode_with_progress_window(passes, duration, work_dir, video_name, output_file)
        else:
            def report(fraction, remaining):
                mins, secs = divmod(int(remaining), 60) if remaining is not None else (None, None)
                gui_progress(int(fraction * 100), mins, secs)
            ok = _encode(passes, duration, work_dir, report)
            if ok:
                print(Fore.GREEN + f"\n✅ Compression finished. Output: {output_file}" + Style.RESET_ALL)
        if not ok and os.path.exists(output_path):
            os.remove(output_path)  # a failed encode leaves an unreadable file that looks like a result
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def build_two_pass_commands(input_path, output_path, ext, video_bitrate_kbps, sub_option, sub_path, work_dir,
                            fps_mode="-fps_mode"):
    """
    ffmpeg commands of a two-pass encode: the first pass only analyses the video, the second one
    uses these statistics to distribute the bits and hit the target size (a single pass can overshoot it).
    Both passes must encode exactly the same frames: the timestamps are passed through, otherwise
    the MP4 output of the second pass can duplicate a frame that the first pass did not analyse
    (x264 then fails with "Incomplete MB-tree stats file" or even hangs).
    fps_mode is the option name given by utils.fps_mode_option().
    Returns:
        list: (command, share of the total work) for each pass.
    """
    video_args = []
    if sub_option == "hard" and sub_path:
        # Plain relative name, resolved in the working directory: no filter escaping needed
        video_args += ["-vf", f"subtitles={os.path.basename(sub_path)}"]
    video_args += [fps_mode, "passthrough",
                   "-c:v", "libx264", "-b:v", f"{video_bitrate_kbps}k", "-preset", "medium",
                   "-passlogfile", os.path.join(work_dir, "ffmpeg2pass")]
    if sub_option == "soft" and sub_path:
        inputs = ["-i", input_path, "-i", sub_path]
        maps = ["-map", "0:v", "-map", "0:a?", "-map", "1:s"]
        video_maps = ["-map", "0:v"]  # both passes must encode the same video streams
        # mov_text is the only text subtitle codec of MP4, MKV takes SRT/ASS as they are
        subtitle_args = ["-c:s", "mov_text" if ext == "mp4" else "copy"]
    else:
        inputs, maps, video_maps, subtitle_args = ["-i", input_path], [], [], []
    audio_args = ["-c:a", "aac", "-ac", "2", "-ar", "48000", "-b:a", f"{AUDIO_BITRATE // 1000}k"]
    pass1 = ["ffmpeg", "-y", "-i", input_path, *video_maps, *video_args, "-pass", "1", "-an", "-sn", "-f", "null", "-"]
    pass2 = ["ffmpeg", "-y", *inputs, *maps, *video_args, "-pass", "2", *audio_args, *subtitle_args,
             "-movflags", "+faststart", output_path]
    return [(pass1, FIRST_PASS_SHARE), (pass2, 1 - FIRST_PASS_SHARE)]


def _encode(passes, duration, work_dir, report):
    """
    Run the passes one after the other; report(fraction of the whole job, seconds left or None)
    is called on each ffmpeg progress line. Returns True on success.
    """
    start_time = time.time()
    done = 0.0
    for step, (cmd, share) in enumerate(passes, 1):
        # ffmpeg writes UTF-8 (file names): the locale encoding (cp1252 on Windows) could fail on it
        proc = subprocess.Popen(cmd, cwd=work_dir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace")
        last_lines = collections.deque(maxlen=8)  # shown if ffmpeg fails
        last_output = [time.time()]
        stalled = threading.Event()

        def watchdog():
            # A stuck ffmpeg ignores the usual termination request: kill it
            while proc.poll() is None:
                if time.time() - last_output[0] > STALL_TIMEOUT:
                    stalled.set()
                    proc.kill()
                    return
                time.sleep(1)
        threading.Thread(target=watchdog, daemon=True).start()
        for line in proc.stderr:  # progress lines end with \r, split like \n
            last_output[0] = time.time()
            last_lines.append(line.rstrip())
            match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
            if match:
                h, m, s = match.groups()
                fraction = done + share * min(1.0, (int(h) * 3600 + int(m) * 60 + float(s)) / duration)
                elapsed = time.time() - start_time
                report(fraction, elapsed / fraction - elapsed if fraction > 0 else None)
        proc.wait()
        if proc.returncode != 0:
            reason = f"ffmpeg stopped responding for {STALL_TIMEOUT} s and was killed" if stalled.is_set() else "\n".join(last_lines)
            print(Fore.RED + f"\n❌ Compression failed (pass {step}):\n{reason}" + Style.RESET_ALL)
            return False
        done += share
    report(1.0, 0)
    return True


def _encode_with_progress_window(passes, duration, work_dir, video_name, output_file):
    """Encode in a worker thread while a progress window (and a console bar) shows the progress. Returns True on success."""
    import tkinter as tk
    import tkinter.ttk as ttk
    events = queue.Queue()  # the worker thread never touches Tk: it only fills this queue
    result = {"ok": False}

    root = tk._default_root
    progress_win = tk.Toplevel(root) if root is not None and root.winfo_exists() else tk.Tk()
    progress_win.title("Compression Progress")
    progress_win.geometry("420x150")
    progress_win.attributes('-topmost', True)
    apply_modern_theme(progress_win)
    frame = create_styled_frame(progress_win)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    create_styled_label(frame, text=f"Compressing: {video_name}", style='Title.TLabel').pack(pady=(0, 8))
    progress_var = tk.DoubleVar(master=progress_win)
    ttk.Progressbar(frame, variable=progress_var, maximum=100, length=350, style='TProgressbar').pack(pady=6)
    percent_label = create_styled_label(frame, text="0%", style='TLabel')
    percent_label.pack()
    time_label = create_styled_label(frame, text="Estimated time left: --:--", style='TLabel', font=("Segoe UI", 10, "italic"))
    time_label.pack()

    def show(fraction, remaining):
        percent = int(fraction * 100)
        eta = "--:--" if remaining is None else "{:02d}:{:02d}".format(*divmod(int(remaining), 60))
        progress_var.set(percent)
        percent_label.config(text=f"{percent}%")
        time_label.config(text=f"Estimated time left: {eta}")
        bar_len = 40
        filled = int(round(bar_len * fraction))
        sys.stdout.write(f"\rCompressing: [{'=' * filled}{'-' * (bar_len - filled)}] {percent}% | ETA: {eta}")
        sys.stdout.flush()

    def worker():
        ok = False
        try:
            ok = _encode(passes, duration, work_dir, lambda *progress: events.put(("progress", *progress)))
        finally:
            events.put(("done", ok))

    def poll():
        try:
            while True:
                event = events.get_nowait()
                if event[0] == "progress":
                    show(*event[1:])
                else:
                    print()
                    result["ok"] = event[1]
                    if event[1]:
                        print(Fore.GREEN + f"\n✅ Compression finished. Output: {output_file}" + Style.RESET_ALL)
                    progress_win.after(500, progress_win.destroy)
                    return
        except queue.Empty:
            pass
        progress_win.after(200, poll)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    poll()
    progress_win.wait_window()
    thread.join()
    return result["ok"]
