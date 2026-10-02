"""
Audio codecs offered by the audio conversion (and the compression): their ffmpeg encoder, the channel
layouts they take, the containers that can store them, and the ffmpeg arguments that encode a list of
audio tracks with the choices of the user.
"""
import functools
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioCodec:
    name: str           # short name, also used in the name of the output file
    label: str          # shown to the user
    encoder: str        # ffmpeg encoder
    layouts: str        # channel layouts given to aformat when the surround is kept ("" = any layout works)
    lossless: bool = False  # no bitrate to choose
    mp4: bool = True    # can be stored in MP4 (otherwise the output is an MKV)


CODECS = [
    AudioCodec("aac", "AAC: plays everywhere", "aac", "mono|stereo|5.1|7.1"),
    AudioCodec("opus", "Opus: best quality per kbps (a third less than AAC), not on old devices", "libopus",
               "mono|stereo|5.1|7.1"),
    AudioCodec("ac3", "AC3 (Dolby Digital): home cinemas and TVs, 5.1 at most", "ac3", "mono|stereo|5.1"),
    AudioCodec("eac3", "E-AC3 (Dolby Digital Plus): more efficient than AC3, recent TVs, 5.1 at most", "eac3",
               "mono|stereo|5.1"),
    AudioCodec("flac", "FLAC: lossless, large files (MKV)", "flac", "", lossless=True, mp4=False),
]
# Why the layouts: the 5.1(side) of DTS/AC3 tracks is an unknown layout for AAC and is refused by Opus,
# and AC3/E-AC3 would turn a 7.1 track into 5.0 without its LFE: aformat converts them to these layouts.
BY_NAME = {codec.name: codec for codec in CODECS}
KBPS_CHOICES = (96, 128, 160, 192, 256, 320)  # per stereo track


@dataclass(frozen=True)
class AudioSettings:
    """Choices of the user for the audio tracks."""
    codec: str = "aac"
    kbps: int = 160              # per stereo or mono track (surround tracks get twice as much)
    keep_surround: bool = False  # keep the 5.1/7.1 channels instead of the stereo down-mix


def bitrates(tracks, settings):
    """Bitrate (bps) of each of the tracks once encoded, or None for a lossless codec."""
    if BY_NAME[settings.codec].lossless:
        return [None] * len(tracks)
    return [settings.kbps * 1000 * (2 if settings.keep_surround and (track.channels or 2) > 2 else 1)
            for track in tracks]


def encode_args(tracks, settings):
    """ffmpeg arguments that encode the audio tracks (in output order) with the settings."""
    codec = BY_NAME[settings.codec]
    args = ["-c:a", codec.encoder]
    if not codec.lossless:
        args += ["-ar", "48000"]  # the rate of video soundtracks, and one that Opus takes
    if not settings.keep_surround:
        args += ["-ac", "2"]
    elif codec.layouts:
        args += ["-af", f"aformat=channel_layouts={codec.layouts}"]
    for index, bps in enumerate(bitrates(tracks, settings)):
        if bps:
            args += [f"-b:a:{index}", f"{bps // 1000}k"]
    return args


def output_extension(source_ext, codec_name):
    """Extension of the output: MP4/MOV stay (unless the codec cannot go in MP4), anything else becomes MKV."""
    source_ext = source_ext.lower()
    if source_ext in (".mp4", ".m4v", ".mov") and BY_NAME[codec_name].mp4:
        return source_ext
    return ".mkv"


def _built_audio_encoders():
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True,
                             encoding="utf-8", errors="replace").stdout
    except OSError:
        return set()
    return {line.split()[1] for line in out.splitlines() if len(line.split()) > 1 and line.startswith(" A")}


@functools.lru_cache(maxsize=None)
def available_codecs():
    """The codecs whose encoder is in this ffmpeg build (libopus may be missing), AAC first."""
    built = _built_audio_encoders()
    return [codec for codec in CODECS if codec.encoder in built] or [BY_NAME["aac"]]
