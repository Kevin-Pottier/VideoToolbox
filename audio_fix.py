"""
audio_fix.py
-----------------

This module provides functionality to down‑mix the audio tracks of a
video file to stereo AAC streams while leaving the video stream
untouched.  Every audio track, subtitle and attachment is kept, and the
French audio tracks are moved first (the first one becomes the default
track), the other tracks keep their order.  The primary use case for this function is to convert
files that carry multi‑channel audio (e.g. 5.1 surround) into a
two‑channel stereo layout which is broadly compatible with mobile
players such as Telegram.  The implementation is inspired by the
existing `compression.py` module in this repository and follows the
same conventions for logging, progress reporting and helper
usage.

Key features:

* Reads the streams (languages, duration) via ``ffprobe`` to order the
  audio tracks and drive progress reporting when run without a GUI progress callback.
* Constructs an ``ffmpeg`` command that copies the video stream
  untouched (``-c:v copy``) and re‑encodes every audio stream to AAC
  stereo with a configurable bitrate and sample rate, French first.
* Optionally updates a GUI or CLI progress bar by parsing the
  ``ffmpeg`` stderr output for timestamps.

Example usage from another module:

    from audio_fix import run_audio_fix
    run_audio_fix("my_video.mp4")

The above call will produce a file named ``my_video_fixed.mp4`` in
the same directory.
"""

import os
import subprocess
import threading
from typing import Callable, Optional

try:
    # Use colorama for coloured terminal output when available.  This
    # dependency is optional; if it is not installed the script will
    # fall back to plain text.
    from colorama import Fore, Style  # type: ignore
except ImportError:
    class _Ansi:
        def __getattr__(self, name: str) -> str:
            return ''
    Fore = _Ansi()  # type: ignore
    Style = _Ansi()  # type: ignore

from audio_tracks import ffprobe_streams, french_first, is_french_track

# Disposition flags kept when the default flag of a track changes. ffmpeg replaces all the flags
# of a stream given with -disposition, and these names are understood by old ffmpeg versions too.
KEPT_DISPOSITION_FLAGS = ("dub", "original", "comment", "lyrics", "karaoke", "forced", "hearing_impaired",
                          "visual_impaired", "clean_effects", "captions", "descriptions", "dependent", "metadata")


def _track_label(track) -> str:
    label = (track.language or "?").upper()
    if track.channels:
        label += f" {track.channels}ch"
    if track.title:
        label += f" ({track.title})"
    return label

def build_audio_fix_command(input_path: str, output_file: str, media, audio_channels: int = 2,
                            sample_rate: int = 48_000, audio_bitrate: str = "160k"):
    """
    Build the ffmpeg command of the audio fix: every audio track down-mixed, French tracks first.
    Returns:
        tuple: (command, audio tracks in output order, whether a French track was found)
    """
    # French tracks first. Without -map ffmpeg would keep a single audio track and at most one subtitle.
    audio_tracks = french_first(media.audio_tracks)
    has_french = is_french_track(audio_tracks[0])
    ffmpeg_cmd = ["ffmpeg", "-i", input_path, "-map", "0:v?"]
    for track in audio_tracks:
        ffmpeg_cmd += ["-map", f"0:{track.stream_index}"]
    ffmpeg_cmd += ["-map", "0:s?"]
    if os.path.splitext(output_file)[1].lower() == ".mkv":
        ffmpeg_cmd += ["-map", "0:t?"]  # attachments (fonts of ASS subtitles)
    ffmpeg_cmd += [
        "-c", "copy",
        "-c:a", "aac",
        "-ac", str(audio_channels),
        "-ar", str(sample_rate),
        "-b:a", audio_bitrate,
    ]
    if has_french:
        # The first French track becomes the default one, the other flags of each track are kept
        for out_index, track in enumerate(audio_tracks):
            should_be_default = out_index == 0
            if track.is_default != should_be_default:
                flags = [flag for flag in track.disposition_flags if flag in KEPT_DISPOSITION_FLAGS]
                if should_be_default:
                    flags.insert(0, "default")
                ffmpeg_cmd += [f"-disposition:a:{out_index}", "+".join(flags) or "0"]
    ffmpeg_cmd += [
        "-movflags", "+faststart",
        output_file,
        "-y"
    ]
    return ffmpeg_cmd, audio_tracks, has_french


def run_audio_fix(file_path: str,
                  audio_channels: int = 2,
                  sample_rate: int = 48_000,
                  audio_bitrate: str = "160k",
                  gui_progress: Optional[Callable[[float, Optional[int], Optional[int]], None]] = None
                  ) -> list[str]:
    """
    Convert the audio tracks of the given video file to AAC stereo while
    leaving the video track untouched, French tracks first.  A progress bar will be
    displayed in the terminal unless a ``gui_progress`` callback is
    provided.  Upon successful completion a new file is written next
    to the original one with ``_fixed`` appended to the base name.

    Parameters
    ----------
    file_path:
        Path to the video file to be processed.
    audio_channels:
        Number of channels in the output audio.  Defaults to 2 (stereo).
    sample_rate:
        Audio sample rate in Hz.  Defaults to 48 kHz.
    audio_bitrate:
        Target audio bitrate (e.g. ``"160k"``).  Defaults to 160 kbit/s.
    gui_progress:
        Optional callback taking ``percent``, ``mins`` and ``secs``.  If
        provided, the function assumes the caller will handle GUI
        updates and no terminal progress bar will be printed.

    Returns
    -------
    list[str]
        Labels of the audio tracks in their output order (e.g. ``"FRE 6ch"``).

    Raises
    ------
    RuntimeError
        If the file cannot be read, has no audio track, or if ``ffmpeg``
        returns a non‑zero exit code.
    """
    # Normalize path and determine output filename
    abs_path = os.path.abspath(file_path)
    base, ext = os.path.splitext(abs_path)
    # Use .mp4 extension if original extension is missing or unknown
    output_ext = ext if ext else ".mp4"
    output_file = f"{base}_fixed{output_ext}"

    # Streams and duration (the duration drives the progress estimation)
    media = ffprobe_streams(abs_path)
    if not media.audio_tracks:
        raise RuntimeError("no audio track to fix")
    duration = media.duration if media.duration and media.duration > 0 else None
    if duration is None:
        print(Fore.RED + f"Could not determine video duration for '{file_path}'." + Style.RESET_ALL)

    ffmpeg_cmd, audio_tracks, has_french = build_audio_fix_command(
        abs_path, output_file, media, audio_channels, sample_rate, audio_bitrate)
    track_order = [_track_label(track) for track in audio_tracks]

    print(Fore.YELLOW + f"\nRunning audio fix for: {os.path.basename(file_path)}" + Style.RESET_ALL)
    print("\tAudio tracks: " + ", ".join(track_order) + ("" if has_french else " (no French track found, order kept)"))
    print("\tCommand:", " ".join(ffmpeg_cmd))

    def run_ffmpeg_and_report() -> None:
        """Internal helper to execute ffmpeg and report progress."""
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        bar_len = 40
        start_time = None
        # Only attempt progress tracking if duration is known
        while True:
            line = proc.stderr.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            if "time=" in line and duration:
                # Parse timestamps of the form time=00:01:23.45
                import re, time
                match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                if match:
                    h, m, s = match.groups()
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    if start_time is None:
                        start_time = time.time()
                    percent = min(100, (current_time / duration) * 100)
                    elapsed = time.time() - start_time if start_time else 0
                    if current_time > 0 and percent < 100:
                        est_total = elapsed / (percent / 100)
                        remaining = est_total - elapsed
                        mins, secs = divmod(int(remaining), 60)
                    else:
                        mins = secs = 0
                    if gui_progress:
                        # Forward progress to GUI callback
                        try:
                            gui_progress(percent, mins, secs)
                        except Exception:
                            pass
                    else:
                        # Draw CLI progress bar
                        filled_len = int(round(bar_len * percent / 100))
                        bar = '=' * filled_len + '-' * (bar_len - filled_len)
                        print(f'\rFixing audio: [{bar}] {percent:5.1f}% | ETA: {mins:02d}:{secs:02d}', end='', flush=True)
        proc.wait()
        # Ensure progress bar finishes at 100%
        if not gui_progress and duration:
            bar = '=' * bar_len
            print(f'\rFixing audio: [{bar}] 100.0% | ETA: 00:00')
        if proc.returncode == 0:
            print(Fore.GREEN + f"\n✅ Audio fix completed. Output: {output_file}" + Style.RESET_ALL)
        else:
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")

    if gui_progress:
        # When running in GUI mode we run ffmpeg synchronously; GUI callback will update progress
        run_ffmpeg_and_report()
    else:
        # Use a background thread to avoid blocking when a progress bar window is open
        errors: list[Exception] = []

        def run_in_thread() -> None:
            try:
                run_ffmpeg_and_report()
            except Exception as e:  # re-raised below: an exception does not leave a thread by itself
                errors.append(e)
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        if errors:
            raise errors[0]
    return track_order

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Down‑mix video audio to AAC stereo")
    parser.add_argument("file", help="Path to the video file to fix")
    parser.add_argument("--bitrate", default="160k", help="Audio bitrate, e.g. 160k")
    parser.add_argument("--channels", type=int, default=2, help="Number of audio channels")
    parser.add_argument("--sample_rate", type=int, default=48000, help="Audio sample rate in Hz")
    args = parser.parse_args()
    run_audio_fix(args.file, audio_channels=args.channels, sample_rate=args.sample_rate, audio_bitrate=args.bitrate)