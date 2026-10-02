"""
audio_conversion.py
-------------------

Convert the audio tracks of a video file without touching its video: every audio track is encoded with
the chosen codec (AAC, Opus, AC3, E-AC3 or FLAC, see audio_codecs), at the chosen bitrate, down-mixed to
stereo or with its 5.1/7.1 channels kept. Every audio track, subtitle and attachment is kept, the French
audio tracks are moved first (the first one becomes the default track), the other tracks keep their order.

Typical uses: AC3/DTS tracks that a phone, a browser or a TV cannot play (to AAC), multichannel audio for
stereo players (Telegram...), smaller files (Opus), or a lossless copy (FLAC).

Example:

    from audio_conversion import run_audio_conversion
    from audio_codecs import AudioSettings
    run_audio_conversion("my_video.mkv", AudioSettings("opus", 128, keep_surround=True))

writes my_video_opus.mkv next to the original (MP4/MOV files stay MP4/MOV when the codec allows it,
the others become MKV).
"""

import os
import re
import subprocess
import threading
import time
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

import audio_codecs
from audio_codecs import AudioSettings
from audio_tracks import ffprobe_streams, french_default_dispositions, french_first, is_french_track
from utils import COPY_INPUT_FLAGS


def _track_label(track) -> str:
    label = (track.language or "?").upper()
    if track.channels:
        label += f" {track.channels}ch"
    if track.title:
        label += f" ({track.title})"
    return label


def output_path(file_path: str, settings: AudioSettings) -> str:
    """my_video.mkv -> my_video_opus.mkv, next to the original (see audio_codecs.output_extension)."""
    base, ext = os.path.splitext(os.path.abspath(file_path))
    return f"{base}_{settings.codec}{audio_codecs.output_extension(ext, settings.codec)}"


def build_conversion_command(input_path: str, output_file: str, media, settings: AudioSettings = AudioSettings()):
    """
    Build the ffmpeg command of the conversion: every audio track encoded, French tracks first, the rest copied.
    Returns:
        tuple: (command, audio tracks in output order, whether a French track was found)
    """
    # French tracks first. Without -map ffmpeg would keep a single audio track and at most one subtitle.
    audio_tracks = french_first(media.audio_tracks)
    has_french = is_french_track(audio_tracks[0])
    to_mkv = output_file.lower().endswith(".mkv")
    ffmpeg_cmd = ["ffmpeg", *COPY_INPUT_FLAGS, "-i", input_path, "-map", "0:v?"]
    for track in audio_tracks:
        ffmpeg_cmd += ["-map", f"0:{track.stream_index}"]
    ffmpeg_cmd += ["-map", "0:s?"]
    if to_mkv:
        ffmpeg_cmd += ["-map", "0:t?"]  # attachments (fonts of ASS subtitles)
    ffmpeg_cmd += ["-c", "copy", *audio_codecs.encode_args(audio_tracks, settings)]
    if to_mkv:
        # The mov_text subtitles of an MP4 cannot be copied into MKV
        for index, track in enumerate(media.subtitle_tracks):
            if track.codec == "mov_text":
                ffmpeg_cmd += [f"-c:s:{index}", "srt"]
    # The first French track becomes the default one, the other flags of each track are kept
    ffmpeg_cmd += french_default_dispositions(audio_tracks)
    if not to_mkv:
        ffmpeg_cmd += ["-movflags", "+faststart"]
    ffmpeg_cmd += [output_file, "-y"]
    return ffmpeg_cmd, audio_tracks, has_french


def run_audio_conversion(file_path: str, settings: AudioSettings = AudioSettings(),
                         gui_progress: Optional[Callable[[float, Optional[int], Optional[int]], None]] = None):
    """
    Convert the audio tracks of the video file, the video untouched, French tracks first. A progress bar
    is shown in the terminal unless a gui_progress(percent, mins, secs) callback is given.

    Returns:
        tuple: (path of the output file, labels of the audio tracks in their output order, e.g. "FRE 6ch")
    Raises:
        RuntimeError: if the file cannot be read, has no audio track, or if ffmpeg fails (no output is left).
    """
    abs_path = os.path.abspath(file_path)
    output_file = output_path(abs_path, settings)

    # Streams and duration (the duration drives the progress estimation)
    media = ffprobe_streams(abs_path)
    if not media.audio_tracks:
        raise RuntimeError("no audio track to convert")
    duration = media.duration if media.duration and media.duration > 0 else None
    if duration is None:
        print(Fore.RED + f"Could not determine video duration for '{file_path}'." + Style.RESET_ALL)

    ffmpeg_cmd, audio_tracks, has_french = build_conversion_command(abs_path, output_file, media, settings)
    track_order = [_track_label(track) for track in audio_tracks]

    print(Fore.YELLOW + f"\nConverting the audio of: {os.path.basename(file_path)}" + Style.RESET_ALL)
    print("\tAudio tracks: " + ", ".join(track_order) + ("" if has_french else " (no French track found, order kept)"))
    print("\tCommand:", " ".join(ffmpeg_cmd))

    def run_ffmpeg_and_report() -> None:
        """Execute ffmpeg and report its progress."""
        # ffmpeg writes UTF-8 (file names): the locale encoding (cp1252 on Windows) could fail on it
        proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace")
        bar_len = 40
        start_time = None
        last_lines = []
        for line in proc.stderr:  # progress lines end with \r, split like \n
            last_lines = (last_lines + [line.rstrip()])[-8:]
            match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
            if not (match and duration):
                continue
            h, m, s = match.groups()
            current_time = int(h) * 3600 + int(m) * 60 + float(s)
            if start_time is None:
                start_time = time.time()
            percent = min(100, (current_time / duration) * 100)
            elapsed = time.time() - start_time
            if current_time > 0 and percent < 100:
                mins, secs = divmod(int(elapsed / (percent / 100) - elapsed), 60)
            else:
                mins = secs = 0
            if gui_progress:
                gui_progress(percent, mins, secs)
            else:
                filled_len = int(round(bar_len * percent / 100))
                bar = '=' * filled_len + '-' * (bar_len - filled_len)
                print(f'\rConverting audio: [{bar}] {percent:5.1f}% | ETA: {mins:02d}:{secs:02d}', end='', flush=True)
        proc.wait()
        if not gui_progress and duration:
            print(f'\rConverting audio: [{"=" * bar_len}] 100.0% | ETA: 00:00')
        if proc.returncode == 0:
            print(Fore.GREEN + f"\n✅ Audio conversion completed. Output: {output_file}" + Style.RESET_ALL)
        else:
            if os.path.exists(output_file):
                os.remove(output_file)  # a failed ffmpeg leaves an unreadable file that looks like a result
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}:\n" + "\n".join(last_lines[-3:]))

    if gui_progress:
        # The GUI runs this function in a worker thread already
        run_ffmpeg_and_report()
    else:
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
    return output_file, track_order


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert the audio tracks of a video, the video untouched")
    parser.add_argument("file", help="Path to the video file")
    parser.add_argument("--codec", default="aac", choices=[codec.name for codec in audio_codecs.CODECS])
    parser.add_argument("--kbps", type=int, default=160, help="bitrate per stereo track (surround: twice)")
    parser.add_argument("--keep-surround", action="store_true", help="keep the 5.1/7.1 channels instead of stereo")
    args = parser.parse_args()
    run_audio_conversion(args.file, AudioSettings(args.codec, args.kbps, args.keep_surround))
