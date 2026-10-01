"""
Compare the video encoders that work on this computer, on an extract of one of your videos.

Each encoder compresses the same extract at the same bitrate, with the exact commands of the
compression mode; the script reports its speed, the quality of the result compared with the extract
(SSIM, PSNR, and VMAF when FFmpeg has it) and how close the size is to the target.

Usage:
    python scripts/benchmark_encoders.py my_movie.mkv                 # 30 s from 5 min, 2500 kbps
    python scripts/benchmark_encoders.py my_movie.mkv --start 600 --duration 60 --kbps 1500
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import encoders  # noqa: E402
from audio_tracks import ffprobe_streams  # noqa: E402
from compression import AUDIO_BITRATE, build_encode_commands  # noqa: E402
from utils import COPY_INPUT_FLAGS, fps_mode_option  # noqa: E402


def has_vmaf():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, encoding="utf-8",
                         errors="replace").stdout
    return " libvmaf " in out


def quality(encoded, reference, vmaf):
    """SSIM (dB), PSNR (dB) and VMAF (or None) of the encoded video against the reference."""
    graph = "[0:v][1:v]ssim;[0:v][1:v]psnr"
    if vmaf:
        graph += ";[0:v][1:v]libvmaf"
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", encoded, "-i", reference, "-lavfi", graph, "-f", "null", "-"],
                         capture_output=True, encoding="utf-8", errors="replace").stderr
    ssim = re.search(r"SSIM .*All:[\d.]+ \(([\d.]+|inf)\)", out)
    psnr = re.search(r"PSNR .*average:([\d.]+|inf)", out)
    vmaf_score = re.search(r"VMAF score: ([\d.]+)", out)
    def fmt(match):
        return f"{float(match.group(1)):.2f}" if match and match.group(1) != "inf" else "?"
    return fmt(ssim), fmt(psnr), fmt(vmaf_score) if vmaf else None


def main():
    parser = argparse.ArgumentParser(description="Compare the video encoders that work on this computer.")
    parser.add_argument("video", help="a video of yours (a movie gives the most representative results)")
    parser.add_argument("--start", type=float, default=300, help="start of the extract in seconds (default 300)")
    parser.add_argument("--duration", type=float, default=30, help="length of the extract in seconds (default 30)")
    parser.add_argument("--kbps", type=int, default=2500, help="video bitrate given to every encoder (default 2500)")
    args = parser.parse_args()

    work_dir = tempfile.mkdtemp(prefix="videotoolbox_bench_")
    try:
        extract = os.path.join(work_dir, "extract.mkv")
        # Stream copy: fast and lossless (the extract starts on the keyframe before --start)
        subprocess.run(["ffmpeg", "-v", "error", "-y", *COPY_INPUT_FLAGS, "-ss", str(args.start), "-i", args.video,
                        "-t", str(args.duration),
                        "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", extract], check=True)
        media = ffprobe_streams(extract)
        video = media.video_tracks[0]
        frames = int(subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0",
                                     "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", extract],
                                    capture_output=True, text=True).stdout.strip())
        print(f"Extract: {video.width}x{video.height}, {frames} frames, {media.duration:.1f} s, "
              f"video at {args.kbps} kbps")
        print("Detecting the encoders...")
        available = encoders.available_encoders()
        vmaf = has_vmaf()
        target_bytes = (args.kbps * 1000 + AUDIO_BITRATE * min(1, len(media.audio_tracks))) * media.duration / 8
        print(f"\n{'Encoder':34s} {'Speed':>12s} {'SSIM':>9s} {'PSNR':>9s}" + (f" {'VMAF':>6s}" if vmaf else "")
              + f" {'Size/target':>12s}")
        for encoder in available:
            output = os.path.join(work_dir, f"out_{encoder.name}.mkv")
            passes = build_encode_commands(extract, output, "mkv", args.kbps, "none", None, work_dir, media,
                                           fps_mode_option(), encoder)
            start = time.time()
            try:
                for cmd, _ in passes:
                    subprocess.run([cmd[0], "-v", "error", *cmd[1:]], cwd=work_dir, check=True,
                                   capture_output=True, encoding="utf-8", errors="replace")
            except subprocess.CalledProcessError as e:
                print(f"{encoder.label:34s} failed: {e.stderr.strip().splitlines()[-1] if e.stderr.strip() else e}")
                continue
            elapsed = time.time() - start
            ssim, psnr, vmaf_score = quality(output, extract, vmaf)
            speed = f"{frames / elapsed:.0f} fps x{media.duration / elapsed:.1f}"
            ratio = os.path.getsize(output) / target_bytes * 100
            print(f"{encoder.label:34s} {speed:>12s} {ssim:>6s} dB {psnr:>6s} dB"
                  + (f" {vmaf_score:>6s}" if vmaf else "") + f" {ratio:>11.0f}%")
            os.remove(output)
        print("\nSpeed: frames per second, and how many times faster than real time (x1 = the duration of the video).")
        print("Quality: the higher the better; at the same bitrate, the better encoder gives the higher values.")
        print("Size/target: on a short extract the encoders deviate more than on a whole movie (a few %).")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
