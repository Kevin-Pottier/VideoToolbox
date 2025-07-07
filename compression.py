import os
from colorama import Fore, Style
from utils import ffprobe
import subprocess

def run_compression(file_path, sub_option, sub_file, ext, max_size_gb):
    def ffmpeg_escape(path):
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

    # Run ffmpeg in the video's directory so all relative paths work
    ret = subprocess.call(ffmpeg_cmd, cwd=video_dir)

    if ret == 0:
        print(Fore.GREEN + f"\n✅ Compression finished. Output: {output_file}" + Style.RESET_ALL)
    else:
        print(Fore.RED + f"\n❌ Compression failed." + Style.RESET_ALL)
