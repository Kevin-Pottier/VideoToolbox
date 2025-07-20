import os
from colorama import Fore, Style
from utils import ffprobe
import subprocess

def run_compression(file_path, sub_option, sub_file, ext, max_size_gb, gui_progress=None):
    """
    Compress a video file using FFmpeg, with optional subtitle handling and GUI/CLI progress bars.
    Args:
        file_path (str): Path to the video file.
        sub_option (str): Subtitle option ('none', 'soft', 'hard').
        sub_file (str): Path to the subtitle file (if any).
        ext (str): Output file extension ('mp4' or 'mkv').
        max_size_gb (float): Target maximum file size in GB.
    """
    def ffmpeg_escape(path):
        """
        Escape a file path for FFmpeg compatibility (Windows).
        Args:
            path (str): The file path to escape.
        Returns:
            str: Escaped path.
        """
        # Use forward slashes and escape special chars for FFmpeg
        return os.path.abspath(path).replace("\\", "/").replace(":", "\\:")

    # Metadata extraction
    duration_str = ffprobe([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", file_path
    ])
    try:
        duration = float(duration_str)
        if duration <= 0:
            raise ValueError
    except Exception:
        print(Fore.RED + f"Could not determine video duration (got '{duration_str}'). Aborting." + Style.RESET_ALL)
        return

    audio_bitrate_str = ffprobe([
        "ffprobe", "-v", "error", "-select_streams",
        "a:0", "-show_entries", "stream=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ])
    if not audio_bitrate_str or audio_bitrate_str == "N/A" or audio_bitrate_str == "0":
        print(Fore.YELLOW + "Warning: Could not determine audio bitrate. Using default 128000 bps." + Style.RESET_ALL)
        audio_bitrate = 128000
    else:
        try:
            audio_bitrate = int(audio_bitrate_str)
        except Exception:
            print(Fore.YELLOW + f"Warning: Unexpected audio bitrate value '{audio_bitrate_str}'. Using default 128000 bps." + Style.RESET_ALL)
            audio_bitrate = 128000

    print(f"Duration: {duration:.2f} s")
    print(f"Audio Bitrate: {audio_bitrate} bps")

    # Bitrate calculation
    target_bits = max_size_gb * 1024 * 1024 * 1024 * 8  # in bits
    audio_bits_total = audio_bitrate * duration # in bits
    video_bits_total = target_bits - audio_bits_total # in bits
    video_bitrate = video_bits_total / duration # in bits per second
    video_bitrate_kbps = int(video_bitrate / 1000) # in kbps

    print(f"Target Video Bitrate: {video_bitrate_kbps} kbps")

    output_file = os.path.splitext(file_path)[0] + f"_compressed.{ext}"

    # Build ffmpeg command
    video_dir = os.path.dirname(file_path)
    video_name = os.path.basename(file_path)
    output_name = os.path.basename(output_file)
    # For subtitles, use only the filename and set cwd to video_dir
    if sub_option == "soft":
        sub_filename = os.path.basename(sub_file) if sub_file else None
        ffmpeg_cmd = [
            "ffmpeg", "-i", video_name,
            "-i", sub_filename,
            "-c:s", "mov_text",
            "-map", "0:v", "-map", "0:a", "-map", "1:s",
            "-c:v", "libx264", "-b:v", f"{video_bitrate_kbps}k",
            "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_name, "-y"
        ]
    else:
        ffmpeg_cmd = [
            "ffmpeg", "-i", video_name,
            "-c:v", "libx264", "-b:v", f"{video_bitrate_kbps}k",
            "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart"
        ]
        if sub_option == "hard" and sub_file:
            sub_filename = os.path.basename(sub_file)
            # Always use forward slashes for ffmpeg filter
            ffmpeg_cmd += ["-vf", f"subtitles={sub_filename.replace('\\', '/')}" ]
        ffmpeg_cmd += [output_name, "-y"]

    print(Fore.YELLOW + f"\nRunning ffmpeg with subtitles option: {sub_option}\n\n" + Style.RESET_ALL)
    print("\tCommand:", " ".join(ffmpeg_cmd))
    print()

    # GUI progress bar setup (only if not in batch mode)
    import threading
    import tkinter as tk
    import tkinter.ttk as ttk
    if gui_progress is None:
        # Use Toplevel if a root window exists, else Tk
        try:
            root = tk._default_root
        except AttributeError:
            root = None
        if root is not None and root.winfo_exists():
            progress_win = tk.Toplevel(root)
        else:
            progress_win = tk.Tk()
        progress_win.title("Compression Progress")
        progress_win.geometry("420x150")
        progress_win.attributes('-topmost', True)
        progress_win.configure(bg="#23272e")
        style = ttk.Style(progress_win)
        try:
            style.theme_use('azure-dark')
        except Exception:
            style.theme_use('clam')
            style.configure('TFrame', background="#23272e")
            style.configure('TLabel', background="#23272e", foreground="#f5f6fa", font=("Segoe UI", 11))
            style.configure('Title.TLabel', background="#23272e", foreground="#4fd1c5", font=("Segoe UI", 13, "bold"))
            style.configure('TButton', font=("Segoe UI", 11), padding=6, background="#353b48", foreground="#f5f6fa", borderwidth=0)
            style.map('TButton',
                background=[('active', '#4fd1c5'), ('!active', '#353b48')],
                foreground=[('active', '#23272e'), ('!active', '#f5f6fa')]
            )
            style.configure('TProgressbar', troughcolor="#23272e", background="#4fd1c5", thickness=18)
        frame = ttk.Frame(progress_win, style='TFrame')
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(frame, text=f"Compressing: {video_name}", style='Title.TLabel', background="#23272e").pack(pady=(0, 8))
        progress_var = tk.DoubleVar(master=progress_win)
        progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=duration, length=350, style='TProgressbar')
        progress_bar.pack(pady=6)
        # Overlay a label on top of the progress bar for percent, with matching background
        percent_label = ttk.Label(frame, text="0%", style='TLabel', background="#23272e")
        percent_label.pack()
        time_label = ttk.Label(frame, text="Estimated time left: --:--", style='TLabel', font=("Segoe UI", 10, "italic"), background="#23272e")
        time_label.pack()

        def update_gui(cur_time, percent, mins, secs):
            if not progress_win.winfo_exists():
                return
            try:
                progress_var.set(cur_time)
                percent_label.config(text=f"{percent}%")
                if mins is not None and secs is not None:
                    time_label.config(text=f"Estimated time left: {mins:02d}:{secs:02d}")
                else:
                    time_label.config(text="Estimated time left: --:--")
                progress_win.update_idletasks()
            except Exception:
                pass

        def finalize_gui():
            if not progress_win.winfo_exists():
                return
            try:
                progress_var.set(duration)
                percent_label.config(text="100%")
                time_label.config(text="Estimated time left: 00:00")
                progress_win.update_idletasks()
            except Exception:
                pass
            # Schedule window close after 500ms if still open
            def safe_destroy():
                try:
                    if progress_win.winfo_exists():
                        progress_win.destroy()
                except Exception:
                    pass
            try:
                if progress_win.winfo_exists():
                    progress_win.after(500, safe_destroy)
            except Exception:
                pass

    import sys
    def run_ffmpeg():
        """
        Run FFmpeg as a subprocess, parse its output for progress, and update both GUI and CLI progress bars.
        """
        import time
        proc = subprocess.Popen(ffmpeg_cmd, cwd=video_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        last_time = 0
        start_time = time.time()
        bar_len = 40
        while True:
            line = proc.stderr.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            if "time=" in line:
                import re
                match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                if match:
                    h, m, s = match.groups()
                    cur_time = int(h) * 3600 + int(m) * 60 + float(s)
                    last_time = cur_time
                    percent = min(100, int(cur_time / duration * 100))
                    elapsed = time.time() - start_time
                    if cur_time > 0 and percent < 100:
                        est_total = elapsed / (cur_time / duration)
                        remaining = est_total - elapsed
                        mins, secs = divmod(int(remaining), 60)
                    else:
                        mins, secs = None, None
                    if gui_progress:
                        gui_progress(percent, mins, secs)
                    else:
                        progress_win.after(0, update_gui, cur_time, percent, mins, secs)
                        # CMD progress bar
                        filled_len = int(round(bar_len * cur_time / float(duration)))
                        bar = '=' * filled_len + '-' * (bar_len - filled_len)
                        sys.stdout.write(f'\rCompressing: [{bar}] {percent}% | ETA: {mins if mins is not None else 0:02d}:{secs if secs is not None else 0:02d}')
                        sys.stdout.flush()
        proc.wait()
        # Always set to 100% at the end
        if gui_progress:
            try:
                gui_progress(100, 0, 0)
            except Exception:
                pass
        else:
            progress_win.after(0, finalize_gui)
            # Force CMD progress bar to 100%
            bar_len = 40
            bar = '=' * bar_len
            sys.stdout.write(f'\rCompressing: [{bar}] 100% | ETA: 00:00\n')
            sys.stdout.flush()
        if proc.returncode == 0:
            print(Fore.GREEN + f"\n✅ Compression finished. Output: {output_file}" + Style.RESET_ALL)
        else:
            print(Fore.RED + f"\n❌ Compression failed." + Style.RESET_ALL)

    if gui_progress is None:
        # Use a flag to signal when done
        done_flag = threading.Event()
        def run_ffmpeg_and_finalize():
            run_ffmpeg()
            # Finalize GUI from main thread, only if window still exists
            try:
                if progress_win.winfo_exists():
                    progress_win.after(0, finalize_gui)
            except Exception:
                pass
            done_flag.set()
        thread = threading.Thread(target=run_ffmpeg_and_finalize)
        thread.start()
        progress_win.mainloop()
        thread.join()  # Wait for compression to finish before returning
    else:
        run_ffmpeg()
