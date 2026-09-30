"""Helpers shared by the tests: FFmpeg detection and generation of small test media."""
import json
import shutil
import subprocess

import pytest

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg is not installed",
)


def run_ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def lavfi_video(duration=1, size="64x36", rate="25"):
    return ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={duration}"]


def lavfi_audio(duration=1, frequency=440):
    return ["-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration={duration}"]


def probe(path):
    """ffprobe JSON output (streams and format) of a media file."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def streams_of_type(path, codec_type):
    return [s for s in probe(path)["streams"] if s["codec_type"] == codec_type]


def count_frames(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return int(out.strip())


def subtitle_text(path, index):
    """Text of the subtitle stream 0:s:<index>, converted to SRT by ffmpeg."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", f"0:s:{index}", "-f", "srt", "-"],
        capture_output=True, check=True,
    ).stdout
    return out.decode("utf-8")
