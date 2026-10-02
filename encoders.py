"""
Video encoders offered by VideoToolbox.

CPU encoders work everywhere. GPU encoders (NVIDIA NVENC, AMD AMF, Intel Quick Sync, VAAPI on Linux,
VideoToolbox on macOS) are much faster but depend on the graphics card, its driver and the ffmpeg
build: they are offered only when encoding a test frame with them succeeds (ffmpeg lists the encoders
it was built with, even without the matching hardware).
"""
import functools
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

VAAPI_DEVICE = "/dev/dri/renderD128"


@dataclass(frozen=True)
class Encoder:
    name: str        # ffmpeg encoder name
    codec: str       # 'H.264', 'HEVC' or 'AV1'
    hardware: str    # '' for the CPU, else the GPU family
    two_pass: bool   # True: two-pass encode, the size of the file is hit precisely

    @property
    def label(self):
        where = f"{self.hardware} GPU" if self.hardware else "CPU"
        return f"{self.codec} - {where} ({self.name})"


ENCODERS = [
    Encoder("libx264", "H.264", "", True),
    Encoder("libx265", "HEVC", "", True),
    Encoder("libsvtav1", "AV1", "", False),
    Encoder("h264_nvenc", "H.264", "NVIDIA", False),
    Encoder("hevc_nvenc", "HEVC", "NVIDIA", False),
    Encoder("av1_nvenc", "AV1", "NVIDIA", False),
    Encoder("h264_amf", "H.264", "AMD", False),
    Encoder("hevc_amf", "HEVC", "AMD", False),
    Encoder("av1_amf", "AV1", "AMD", False),
    Encoder("h264_qsv", "H.264", "Intel", False),
    Encoder("hevc_qsv", "HEVC", "Intel", False),
    Encoder("av1_qsv", "AV1", "Intel", False),
    Encoder("h264_vaapi", "H.264", "VAAPI", False),
    Encoder("hevc_vaapi", "HEVC", "VAAPI", False),
    Encoder("av1_vaapi", "AV1", "VAAPI", False),
    Encoder("h264_videotoolbox", "H.264", "Apple", False),
    Encoder("hevc_videotoolbox", "HEVC", "Apple", False),
]
BY_NAME = {encoder.name: encoder for encoder in ENCODERS}
DEFAULT = BY_NAME["libx264"]

# Speed / quality levels offered to the user, and the preset of each encoder for them (by ffmpeg encoder
# name, or by GPU family). "balanced" is what the compression used before the choice existed (AMD aside:
# its "balanced" quality level replaces "quality", which is now the third level). VAAPI and Apple
# VideoToolbox have no such preset.
SPEEDS = ("fast", "balanced", "quality")
PRESETS = {
    "libx264": ("veryfast", "medium", "slower"),
    "libx265": ("veryfast", "medium", "slow"),
    "libsvtav1": ("10", "8", "6"),
    "NVIDIA": ("p3", "p5", "p7"),
    "AMD": ("speed", "balanced", "quality"),
    "Intel": ("faster", "slow", "veryslow"),
}

# Bits per pixel used when a quality level is given as a bitrate (GPU encoders, see quality_args):
# generous values, close to a Blu-ray, so that the encoder is not the limiting factor.
QUALITY_BITS_PER_PIXEL = {"H.264": 0.12, "HEVC": 0.08, "AV1": 0.06}


def input_args(encoder):
    """Options placed before the inputs."""
    return ["-vaapi_device", VAAPI_DEVICE] if encoder.hardware == "VAAPI" else []


def filter_args(encoder, filters=()):
    """-vf for the given filters, plus the conversion every encoder accepts (8-bit 4:2:0)."""
    filters = list(filters)
    if encoder.hardware == "VAAPI":
        filters += ["format=nv12", "hwupload"]  # VAAPI encodes frames that live on the GPU
    else:
        filters += ["format=yuv420p"]  # 10-bit or 4:4:4 sources cannot go to every encoder
    return ["-vf", ",".join(filters)]


def _codec_args(encoder):
    args = ["-c:v", encoder.name]
    if encoder.codec == "HEVC":
        args += ["-tag:v", "hvc1"]  # the tag Apple players require for HEVC in MP4
    return args


def preset(encoder, speed="balanced"):
    """Preset of the encoder for the speed level (see SPEEDS), or None when the encoder has none."""
    levels = PRESETS.get(encoder.name) or PRESETS.get(encoder.hardware)
    return levels[SPEEDS.index(speed)] if levels else None


def bitrate_args(encoder, kbps, speed="balanced"):
    """
    Encode at an average bitrate (kbps), for a target file size, with the preset of the speed level.
    Two-pass encoders add -pass themselves.
    """
    rate = [f"{kbps}k"]
    peaks = ["-maxrate", f"{2 * kbps}k", "-bufsize", f"{4 * kbps}k"]
    name, hw = encoder.name, encoder.hardware
    level = preset(encoder, speed)
    if name in ("libx264", "libx265", "libsvtav1"):
        extra = ["-preset", level, "-b:v", *rate]
    elif hw == "NVIDIA":
        # hq + two passes per frame: the best quality settings of NVENC that stay fast
        extra = ["-preset", level, "-tune", "hq", "-rc", "vbr", "-multipass", "fullres", "-spatial-aq", "1",
                 "-b:v", *rate, *peaks]
    elif hw == "AMD":
        extra = ["-quality", level, "-rc", "vbr_peak", "-b:v", *rate, *peaks]
    elif hw == "Intel":
        extra = ["-preset", level, "-b:v", *rate, *peaks]
    elif hw == "VAAPI":
        extra = ["-rc_mode", "VBR", "-b:v", *rate, *peaks]
    else:  # Apple VideoToolbox
        extra = ["-b:v", *rate]
    return _codec_args(encoder) + extra


def quality_args(encoder, width, height, fps):
    """
    Encode at a high, constant quality (no target size), e.g. for the upscaled videos.
    CPU encoders use their constant rate factor; GPU encoders, whose quality scales differ between
    vendors and codecs, get a generous bitrate computed from the resolution.
    """
    if encoder.name == "libx264":
        return _codec_args(encoder) + ["-preset", "medium", "-crf", "18"]
    if encoder.name == "libx265":
        return _codec_args(encoder) + ["-preset", "medium", "-crf", "20"]
    if encoder.name == "libsvtav1":
        return _codec_args(encoder) + ["-preset", "8", "-crf", "26"]
    kbps = int(width * height * fps * QUALITY_BITS_PER_PIXEL[encoder.codec] / 1000)
    return bitrate_args(encoder, kbps)


def size_margin(encoder):
    """Share of the target size kept free: single-pass encoders hit the size less precisely."""
    return 0.02 if encoder.two_pass else 0.05


def _built_encoders():
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True,
                             encoding="utf-8", errors="replace").stdout
    except OSError:
        return set()
    return {line.split()[1] for line in out.splitlines() if len(line.split()) > 1 and line.startswith(" V")}


def works(encoder, timeout=20):
    """Encode a few test frames with the encoder and its real options: True if ffmpeg succeeds."""
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", *input_args(encoder),
           "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=0.25",
           *filter_args(encoder), *bitrate_args(encoder, 1000), "-f", "null", "-"]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@functools.lru_cache(maxsize=None)
def available_encoders():
    """The encoders that work on this computer, GPU encoders first (tested once, in parallel)."""
    built = _built_encoders()
    candidates = [e for e in ENCODERS if e.name in built]
    if sys.platform != "linux":
        candidates = [e for e in candidates if e.hardware != "VAAPI"]
    with ThreadPoolExecutor(max_workers=max(1, len(candidates))) as executor:
        results = list(executor.map(works, candidates))
    usable = [e for e, ok in zip(candidates, results) if ok]
    return sorted(usable, key=lambda e: e.hardware == "")  # stable: GPU first, then the CPU ones
