import functools
import os
import subprocess

# Tried in this order: UTF-8 (with or without BOM), then Windows-1252, very common for
# French .srt files. Latin-1 never fails and is the last resort.
SUBTITLE_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")

# Stream copies generate the missing timestamps (-fflags +genpts): the AVI files of DivX/XviD movies have
# none on their B-frames, and MKV/MP4 refuse such packets ("Can't write packet with unknown timestamp")
COPY_INPUT_FLAGS = ["-fflags", "+genpts"]


@functools.lru_cache(maxsize=None)
def fps_mode_option():
    """
    The option that sets how ffmpeg handles frame timestamps: '-fps_mode' since FFmpeg 5.1,
    '-vsync' (its deprecated predecessor) on older versions.
    """
    try:
        help_text = subprocess.run(["ffmpeg", "-hide_banner", "-h", "full"], capture_output=True,
                                   encoding="utf-8", errors="replace").stdout
    except OSError:
        return "-fps_mode"
    return "-fps_mode" if "-fps_mode" in help_text else "-vsync"


def read_subtitle_text(path):
    """
    Read a subtitle file whatever its encoding.
    Returns:
        tuple: (text, encoding used)
    """
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in SUBTITLE_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise AssertionError("unreachable: latin-1 decodes any byte")


def prepare_subtitle_file(sub_path, work_dir):
    """
    Copy a subtitle file into work_dir, converted to UTF-8, under a plain name.
    FFmpeg expects UTF-8 subtitles (other encodings lose their accents), and a plain
    name avoids the escaping rules of the 'subtitles' filter (quotes, commas, colons...).
    Returns:
        str: absolute path of the copy ('subtitles.srt' or 'subtitles.ass').
    """
    text, _ = read_subtitle_text(sub_path)
    ext = os.path.splitext(sub_path)[1].lower() or ".srt"
    dest = os.path.join(os.path.abspath(work_dir), "subtitles" + ext)
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return dest
