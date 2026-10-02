"""
HDR videos (HDR10, HLG, the HDR10 base layer of Dolby Vision profile 8) in the compression.

- With an HEVC or AV1 encoder the HDR is kept: 10-bit frames, the color tags of the source, and for x265 and
  SVT-AV1 the HDR10 static metadata (mastering display, content light level) read from the first frame.
- With H.264, with burned subtitles, or on request, the video is converted to SDR (BT.709): tone mapping in
  linear light with zscale (FFmpeg built with zimg, as the gyan.dev builds and the Linux distributions).

An 8-bit H.264 still tagged as HDR, what the compression made before, is not a standard format: washed-out
colors on most screens, banding on the others.
"""
import functools
import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

PQ = "smpte2084"  # HDR10 and Dolby Vision; HLG is "arib-std-b67"

# HDR to SDR: to linear light, BT.709 primaries, Hable tone curve (no desaturation), back to BT.709 8-bit
TONEMAP_FILTER = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
                  "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
SDR_TAGS = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]


@dataclass(frozen=True)
class StaticMetadata:
    """HDR10 static metadata: mastering display (chromaticities, luminance in cd/m²) and content light level."""
    green: tuple
    blue: tuple
    red: tuple
    white: tuple
    max_luminance: Fraction
    min_luminance: Fraction
    max_cll: Optional[int] = None   # brightest pixel of the video (cd/m²)
    max_fall: Optional[int] = None  # brightest frame on average (cd/m²)


def tags(video):
    """Color tags of the source, written in the output (the HDR is kept)."""
    return ["-color_primaries", video.color_primaries or "bt2020", "-color_trc", video.color_transfer,
            "-colorspace", video.color_space or "bt2020nc"]


@functools.lru_cache(maxsize=None)
def has_zscale():
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, encoding="utf-8",
                             errors="replace").stdout
    except OSError:
        return False
    return " zscale " in out


def read_static_metadata(path):
    """The HDR10 static metadata of the first frame of the video, or None when it has none."""
    out = subprocess.run(["ffprobe", "-v", "error", "-read_intervals", "%+#1", "-select_streams", "v:0", "-show_frames",
                          "-show_entries", "frame=side_data_list", "-of", "json", path],
                         capture_output=True, encoding="utf-8", errors="replace").stdout
    try:
        frames = json.loads(out).get("frames", [])
    except json.JSONDecodeError:
        return None
    side_data = {side.get("side_data_type"): side for side in (frames[0].get("side_data_list", []) if frames else [])}
    display = side_data.get("Mastering display metadata")
    if not display or "max_luminance" not in display:
        return None
    light = side_data.get("Content light level metadata", {})

    def point(name):
        return Fraction(display[f"{name}_x"]), Fraction(display[f"{name}_y"])
    return StaticMetadata(point("green"), point("blue"), point("red"), point("white_point"),
                          Fraction(display["max_luminance"]), Fraction(display["min_luminance"]),
                          light.get("max_content"), light.get("max_average"))


def x265_params(video, metadata):
    """x265 parameters of an HDR video (to join with ':' in -x265-params)."""
    params = ["repeat-headers=1"]  # the metadata in every keyframe: a cut or a seek still shows HDR
    if video.color_transfer == PQ:
        params += ["hdr10=1", "hdr10-opt=1"]
        if metadata:
            # Units of HEVC: 0.00002 for the chromaticities, 0.0001 cd/m² for the luminance
            def xy(point):
                return f"({round(point[0] * 50000)},{round(point[1] * 50000)})"
            params.append(f"master-display=G{xy(metadata.green)}B{xy(metadata.blue)}R{xy(metadata.red)}"
                          f"WP{xy(metadata.white)}L({round(metadata.max_luminance * 10000)},"
                          f"{round(metadata.min_luminance * 10000)})")
            if metadata.max_cll is not None:
                params.append(f"max-cll={metadata.max_cll},{metadata.max_fall or 0}")
    return params


def svtav1_params(metadata):
    """-svtav1-params of the HDR10 static metadata (chromaticities and luminance as plain numbers)."""
    if not metadata:
        return []

    def xy(point):
        return f"({float(point[0]):.4f},{float(point[1]):.4f})"
    params = [f"mastering-display=G{xy(metadata.green)}B{xy(metadata.blue)}R{xy(metadata.red)}WP{xy(metadata.white)}"
              f"L({float(metadata.max_luminance):.4f},{float(metadata.min_luminance):.4f})"]
    if metadata.max_cll is not None:
        params.append(f"content-light={metadata.max_cll},{metadata.max_fall or 0}")
    return ["-svtav1-params", ":".join(params)]
