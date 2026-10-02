"""
Add a subtitle file to one or more videos: softcoded (an added track, the video copied, in seconds) or
hardcoded (burned in the picture, the video re-encoded with x264).
"""
import os
import shutil
import tempfile

from colorama import Fore, Style

from ffmpeg_progress import Cancelled, FFmpegError, console_progress, run_ffmpeg
from gui_helpers import ask_subtitles_for, ask_video_files, run_jobs, show_message, show_results


class SubtitleError(RuntimeError):
    """The subtitles could not be added: the message tells why."""


def output_path(video_path, sub_option):
    """film.mkv -> film_with_subtitles.mkv; AVI, FLV, WMV... cannot store text subtitles: MKV for a softcode."""
    ext = os.path.splitext(video_path)[1]
    if sub_option == "soft" and ext.lower() not in (".mp4", ".mov", ".mkv"):
        ext = ".mkv"
    return os.path.splitext(video_path)[0] + f"_with_subtitles{ext}"


def build_command(input_path, output_file, sub_option, sub_name):
    """ffmpeg command adding the subtitle file sub_name (in the working directory of ffmpeg)."""
    from utils import COPY_INPUT_FLAGS
    if sub_option == "soft":
        # Softcode: add the subtitle track, keeping every track of the source
        # (existing subtitles, and the fonts attached to MKV files)
        cmd = ["ffmpeg", *COPY_INPUT_FLAGS, "-i", input_path, "-i", sub_name,
               "-map", "0:v", "-map", "0:a?", "-map", "0:s?", "-map", "0:t?", "-map", "1:s", "-c", "copy"]
        if os.path.splitext(output_file)[1].lower() in (".mp4", ".mov"):
            # mov_text is the only text subtitle codec of MP4/MOV, MKV takes SRT/ASS as they are
            cmd += ["-c:s", "mov_text", "-movflags", "+faststart"]
        return cmd + [output_file, "-y"]
    # Hardcode: burn subtitles into video (plain relative name: no filter escaping needed)
    return ["ffmpeg", "-i", input_path, "-vf", f"subtitles={sub_name}", "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy", output_file, "-y"]


def add_subtitles_to_video(video_path, sub_option, sub_file, progress=None, cancel=None):
    """
    Add subtitles to a video file using FFmpeg.
    Args:
        video_path (str): Path to the video file.
        sub_option (str): 'soft' for softcode (attach), 'hard' for hardcode (burn in).
        sub_file (str): Path to the subtitle file.
        progress (callable): progress(share done, 0 to 1); a bar in the terminal if None.
        cancel (threading.Event): set by the user to stop.
    Returns:
        str: path of the new video.
    Raises:
        SubtitleError: with the reason (no output file is left). Cancelled: cancel was set.
    """
    from audio_tracks import ffprobe_streams
    from utils import prepare_subtitle_file

    output_file = os.path.abspath(output_path(video_path, sub_option))
    try:
        duration = ffprobe_streams(video_path).duration or 0
    except RuntimeError:
        duration = 0  # no progress, the subtitles are added all the same
    # The subtitle file is copied as UTF-8 under a plain name into a temporary folder, used as
    # ffmpeg working directory: any location, file name or encoding then works
    work_dir = tempfile.mkdtemp(prefix="videotoolbox_")
    try:
        try:
            sub_path = prepare_subtitle_file(sub_file, work_dir)
        except OSError as e:
            raise SubtitleError(f"Cannot read the subtitle file {sub_file}: {e}") from e
        cmd = build_command(os.path.abspath(video_path), output_file, sub_option, os.path.basename(sub_path))
        print(Fore.YELLOW + f"\nAdding subtitles ({sub_option}) to: {os.path.basename(video_path)}\n" + Style.RESET_ALL)
        print("\tCommand:", " ".join(cmd))
        try:
            run_ffmpeg(cmd, duration, progress or console_progress("Adding subtitles"), work_dir, cancel)
        except (FFmpegError, Cancelled) as e:
            if os.path.exists(output_file):
                os.remove(output_file)  # a failed ffmpeg leaves an unreadable file that looks like a result
            if isinstance(e, Cancelled):
                raise
            raise SubtitleError(f"ffmpeg failed:\n{e}") from e
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    print(Fore.GREEN + f"\n✅ Subtitles added successfully. Output: {output_file}" + Style.RESET_ALL)
    return output_file


def run_add_subtitles_gui():
    """Videos, then the subtitles of each one, then the additions in parallel with a progress window."""
    paths = ask_video_files()
    if not paths:
        show_message("error", "File Error", "No video files selected. Please choose at least one video file.")
        return
    choices = ask_subtitles_for(paths)
    if choices is None:
        return
    jobs = [(path, option, sub_file) for path, (option, sub_file) in zip(paths, choices) if option != "none"]
    if not jobs:
        show_message("info", "No Subtitles", "No subtitle option selected. Nothing to do.")
        return

    def add(index, report, cancel):
        return add_subtitles_to_video(*jobs[index], progress=report, cancel=cancel)
    results = run_jobs("Adding subtitles", [f"{os.path.basename(path)} ({option})" for path, option, _ in jobs], add,
                       done_text=os.path.basename)
    show_results("Adding subtitles", results)
