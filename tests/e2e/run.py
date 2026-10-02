"""
End-to-end battery: every feature of VideoToolbox driven through its real windows, from the main menu,
on real footage; the outputs are checked with ffprobe.

    python tests/e2e/run.py                  # every scenario (a few minutes, plus the upscaling)
    python tests/e2e/run.py compress audio   # the scenarios whose name starts with these words
    python tests/e2e/run.py --list

The windows open and are clicked automatically: do not use the mouse or the keyboard meanwhile. On Linux
without display, the scenarios run in a virtual one (xvfb-run, package xvfb). The test videos (about 15 MB)
are downloaded on the first run, into the temporary folder of the system, where the outputs of each scenario
stay for inspection (videotoolbox_e2e/work/<scenario>/, the path is printed at the end).
Scenarios that cannot run on this computer are skipped: upscaling without Real-ESRGAN
(python scripts/fetch_deps.py), GPU encoder without GPU, Google Translate refusing the requests.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from fractions import Fraction

import media

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.join(media.BASE, "work")
GIB = 1024 ** 3
SUB_SOFT = ["Softcode", "Choose Subtitle File", "OK"]
SUB_HARD = ["Hardcode", "Choose Subtitle File", "OK"]
X264, X265, AV1 = "encoder:H.264 CPU", "encoder:HEVC CPU", "encoder:AV1 CPU"
SETTINGS = ["OK"]  # compression settings left as they are (balanced, resolution kept, 192 kbps stereo)


def menu(item, *steps):
    return [[item], *steps]


# name: inputs (files of tests/e2e/media/built), the answers of the dialogs and the plan (see drive.py)
SCENARIOS = {
    # ---- Video compression
    "compress-nosub-mp4-x264": dict(inputs=["film.mkv"], videos=["film.mkv"], size="0.008",
        plan=menu("Video Compression", ["OK"], ["MP4"], [X264, "OK"], SETTINGS)),
    "compress-soft-mkv-x265": dict(inputs=["film.mkv", "film.en.srt"], videos=["film.mkv"], subtitles=["film.en.srt"],
        size="0.008", plan=menu("Video Compression", SUB_SOFT, ["MKV"], [X265, "OK"], SETTINGS)),
    "compress-hard-mp4-av1": dict(inputs=["film.mkv", "film.en.srt"], videos=["film.mkv"], subtitles=["film.en.srt"],
        size="0.008", plan=menu("Video Compression", SUB_HARD, ["MP4"], [AV1, "OK"], SETTINGS)),
    "compress-gpu-hevc": dict(inputs=["film.mkv"], videos=["film.mkv"], size="0.008",
        plan=menu("Video Compression", ["OK"], ["MKV"], ["encoder:HEVC GPU", "OK"], SETTINGS)),
    "compress-settings-720p-fast-128k-surround": dict(inputs=["film.mkv"], videos=["film.mkv"], size="0.008",
        plan=menu("Video Compression", ["OK"], ["MKV"], [X264, "OK"], ["Fast", "720p", "128 kbps", "Keep the 5.1", "OK"])),
    "compress-keep-original-audio": dict(inputs=["film.mkv"], videos=["film.mkv"], size="0.008",
        plan=menu("Video Compression", ["OK"], ["MKV"], [X264, "OK"], ["Keep the original audio", "OK"])),
    "compress-constant-quality": dict(inputs=["film.mkv"], videos=["film.mkv"],
        plan=menu("Video Compression", ["OK"], ["MKV"], [X264, "OK"], ["Constant quality, good", "OK"])),
    "compress-copy-shortcut": dict(inputs=["film.mkv"], videos=["film.mkv"], size="1",
        plan=menu("Video Compression", ["OK"], ["MKV"], [X264, "OK"], SETTINGS)),
    "compress-avi-copy-shortcut": dict(inputs=["megamind.avi"], videos=["megamind.avi"], size="1",
        plan=menu("Video Compression", ["OK"], ["MKV"], [X264, "OK"], SETTINGS)),
    "compress-batch-2-files": dict(inputs=["film.mkv", "cockatoo.mp4", "film.en.srt"], videos=["film.mkv", "cockatoo.mp4"],
        subtitles=["film.en.srt"], size="0.004",
        plan=menu("Video Compression", ["film.mkv", "OK"], SUB_SOFT, ["MKV"], [X264, "OK"], SETTINGS)),
    "compress-invalid-sizes-then-too-small": dict(inputs=["cockatoo.mp4"], videos=["cockatoo.mp4"],
        size=["abc", "-1", "0.0004"], plan=menu("Video Compression", ["OK"], ["MP4"], [X264, "OK"], SETTINGS)),
    "compress-size-cancelled": dict(inputs=["cockatoo.mp4"], videos=["cockatoo.mp4"], size=None,
        plan=menu("Video Compression", ["OK"], ["MP4"], [X264, "OK"], SETTINGS)),
    "compress-no-file-chosen": dict(inputs=[], videos=[], plan=menu("Video Compression")),
    # ---- Subtitle translation
    "translate-film-en-fr": dict(inputs=["film.en.srt"], subtitles=["film.en.srt"], fake_google=True,
        plan=menu("Subtitle Translation", ["Google Translate", "Browse Subtitles", "OK"])),
    "translate-batch-2-files": dict(inputs=["film.en.srt", "movie.en.srt"], subtitles=["film.en.srt", "movie.en.srt"],
        fake_google=True, plan=menu("Subtitle Translation", ["Google Translate", "Browse Subtitles", "OK"])),
    "translate-real-google": dict(inputs=["film.en.srt"], subtitles=["film.en.srt"],
        plan=menu("Subtitle Translation", ["Google Translate", "Browse Subtitles", "OK", "wait:Error"])),
    "translate-not-a-subtitle": dict(inputs=["cockatoo.mp4"], subtitles=["cockatoo.mp4"],
        plan=menu("Subtitle Translation", ["Google Translate", "Browse Subtitles", "OK", "wait:Error"])),
    # DeepL (stand-in): the key of the environment is filled in and DeepL is chosen
    "translate-deepl": dict(inputs=["film.en.srt"], subtitles=["film.en.srt"], fake_deepl="ok",
        env={"DEEPL_API_KEY": "battery-key:fx"}, plan=menu("Subtitle Translation", ["Browse Subtitles", "OK"])),
    "translate-deepl-quota-then-google": dict(inputs=["movie.en.srt"], subtitles=["movie.en.srt"], fake_deepl="quota",
        fake_google=True, env={"DEEPL_API_KEY": "battery-key:fx"},
        plan=menu("Subtitle Translation", ["Browse Subtitles", "OK"])),
    # ---- Upscaling with the real Real-ESRGAN
    "upscale-anime-720p-x264": dict(inputs=["megamind_2s.mkv"], videos=["megamind_2s.mkv"], outdir="out", upscale=True,
        plan=menu("Upscale video", ["720p"], ["Animation", "OK"], [X264, "OK"])),
    "upscale-x4plus-1080p-x265": dict(inputs=["megamind_small.mkv"], videos=["megamind_small.mkv"], outdir="out",
        upscale=True, plan=menu("Upscale video", ["1080p"], ["Live action", "OK"], [X265, "OK"])),
    "upscale-refused-at-the-disk-space-question": dict(inputs=["megamind_small.mkv"], videos=["megamind_small.mkv"],
        outdir="out", upscale=True, refuse=["Upscaling", "Not enough disk space"],
        plan=menu("Upscale video", ["1080p"], ["Animation", "OK"], [X264, "OK"])),
    # ---- Audio conversion (the video copied, French first)
    "audio-conversion-default": dict(inputs=["film.mkv"], videos=["film.mkv"],
        plan=menu("Audio conversion", ["Add Files", "Convert", "wait:Finished"])),
    "audio-conversion-opus-surround": dict(inputs=["film.mkv"], videos=["film.mkv"],
        plan=menu("Audio conversion", ["Opus", "128 kbps", "Keep the channels", "Add Files", "Convert", "wait:Finished"])),
    "audio-conversion-divx-ac3-to-aac": dict(inputs=["megamind.avi"], videos=["megamind.avi"],
        plan=menu("Audio conversion", ["Add Files", "Convert", "wait:Finished"])),
    # ---- Add subtitles
    "add-subtitles-soft": dict(inputs=["film.mkv", "film.en.srt"], videos=["film.mkv"], subtitles=["film.en.srt"],
        plan=menu("Add subtitles", SUB_SOFT)),
    "add-subtitles-hard": dict(inputs=["cockatoo.mp4", "film.en.srt"], videos=["cockatoo.mp4"], subtitles=["film.en.srt"],
        plan=menu("Add subtitles", SUB_HARD)),
    "add-subtitles-avi": dict(inputs=["megamind.avi", "film.en.srt"], videos=["megamind.avi"], subtitles=["film.en.srt"],
        plan=menu("Add subtitles", SUB_SOFT)),
    "add-subtitles-batch": dict(inputs=["film.mkv", "cockatoo.mp4", "film.en.srt"], videos=["film.mkv", "cockatoo.mp4"],
        subtitles=["film.en.srt"], plan=menu("Add subtitles", ["film.mkv", "cockatoo.mp4", "OK"], SUB_SOFT, SUB_HARD)),
    # ---- Audio tracks management: drop the English track, French default, MKV
    "audio-tracks-keep-french": dict(inputs=["film.mkv"], videos=["film.mkv"],
        plan=menu("Audio Tracks Management", [["tree", "1", "#1"], ["tree", "2", "#2"], "MKV", "Process"])),
}


class Skipped(Exception):
    """The scenario cannot run on this computer."""


# ---- ffprobe helpers

def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                         capture_output=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def streams(path, kind):
    return [s for s in probe(path)["streams"] if s["codec_type"] == kind]


def duration(path):
    return float(probe(path)["format"]["duration"])


def packet_times(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", path], capture_output=True, encoding="utf-8").stdout
    return sorted(float(t) for t in out.split() if t not in ("N/A", ""))


def frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, encoding="utf-8").stdout
    return int(out.strip().split(",")[0])


def stream_md5(path, spec):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", spec, "-c", "copy", "-f", "md5", "-"],
                          capture_output=True, encoding="utf-8").stdout.strip()


def subtitle_texts(path):
    return [subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", f"0:s:{i}", "-f", "srt", "-"],
                           capture_output=True, encoding="utf-8").stdout for i in range(len(streams(path, "subtitle")))]


def audio_layout(path):
    """(language, channels, default) of each audio track."""
    return [(s.get("tags", {}).get("language"), s.get("channels"), s.get("disposition", {}).get("default"))
            for s in streams(path, "audio")]


def band_psnr(a, b, band):
    """PSNR between the bottom (subtitles) or top band of two videos, at the second subtitle (4.5 s)."""
    y = "ih*0.8" if band == "bottom" else "0"
    # Decoded from the start: a seek gives broken frames in some sources (cockatoo.mp4)
    pick = f"select='gte(t,4.5)',setpts=PTS-STARTPTS,scale=1280:720,crop=iw:ih*0.2:0:{y}"
    out = subprocess.run(["ffmpeg", "-i", a, "-i", b, "-frames:v", "1", "-lavfi", f"[0:v]{pick}[x];[1:v]{pick}[y];[x][y]psnr",
                          "-f", "null", "-"], capture_output=True, encoding="utf-8", errors="replace").stderr
    return float(re.search(r"average:([\d.]+|inf)", out).group(1).replace("inf", "99"))


# ---- checks

def check(name, sc, d, result, new):
    """List of (what, passed, detail); raises Skipped when the scenario could not run here."""
    errors = [e for e in result["events"] if e[0] == "showerror"]
    skipped = [e[1] for e in result["events"] if e[0] == "skip"]
    if skipped:
        raise Skipped(skipped[0])
    c = [("no Python error", result["error"] is None, result["error"] or ""),
         ("every planned step used", not result["unused_steps"], str(result["unused_steps"]))]

    def add(what, passed, detail=""):
        c.append((what, bool(passed), detail))

    def output(pattern):
        found = [f for f in new if re.search(pattern, f)]
        add(f"output {pattern}", len(found) == 1, ", ".join(new))
        return os.path.join(d, found[0]) if len(found) == 1 else None

    def no_errors():
        add("no error shown", not errors, str(errors))

    src = os.path.join(d, sc["videos"][0]) if sc.get("videos") else None
    if name in ("compress-nosub-mp4-x264", "compress-soft-mkv-x265", "compress-hard-mp4-av1", "compress-gpu-hevc",
                "compress-copy-shortcut"):
        no_errors()
        out = output(r"film_compressed\.(mp4|mkv)$")
        if out:
            add("duration kept", abs(duration(out) - duration(src)) < 0.3, f"{duration(out):.2f} s vs {duration(src):.2f} s")
            add("frames kept", frames(out) == frames(src), f"{frames(out)} vs {frames(src)}")
            channels = 6 if name == "compress-copy-shortcut" else 2  # copied, or down-mixed to stereo
            add("both audio tracks, French first and default",
                audio_layout(out) == [("fre", channels, 1), ("eng", 2, 0)], str(audio_layout(out)))
            texts = subtitle_texts(out)
            add("subtitles of the source kept", texts and "Good morning" in texts[-1], f"{len(texts)} subtitle track(s)")
            codec = streams(out, "video")[0]["codec_name"]
            if name == "compress-copy-shortcut":
                add("streams copied", codec == "h264" and os.path.getsize(out) <= os.path.getsize(src) * 1.01, codec)
            else:
                ratio = os.path.getsize(out) / (float(sc["size"]) * GIB)
                add("size <= target", ratio <= 1.0, f"{ratio:.3f} of the target")
                if name != "compress-gpu-hevc":  # a single GPU pass may stay well under the target
                    add("size >= 85 % of the target", ratio >= 0.85, f"{ratio:.3f} of the target")
                wanted = {"x264": "h264", "x265": "hevc", "av1": "av1", "hevc": "hevc"}[name.split("-")[-1]]
                add(f"codec {wanted}", codec == wanted, codec)
            if "-soft-" in name:
                add("added subtitles first and default, then the source ones",
                    len(texts) == 2 and streams(out, "subtitle")[0]["disposition"]["default"] == 1, f"{len(texts)} tracks")
            if "-hard-" in name:
                bottom, top = band_psnr(out, src, "bottom"), band_psnr(out, src, "top")
                add("subtitles burned (the bottom differs from the source)", bottom < top - 3,
                    f"bottom {bottom:.1f} dB, top {top:.1f} dB")
    elif name == "compress-settings-720p-fast-128k-surround":
        no_errors()
        out = output(r"film_compressed\.mkv$")
        if out:
            video = streams(out, "video")[0]
            add("720p", (video["width"], video["height"]) == (1280, 720), f"{video['width']}x{video['height']}")
            add("frames kept", frames(out) == frames(src), f"{frames(out)} vs {frames(src)}")
            add("French 5.1 kept first, English stereo", audio_layout(out) == [("fre", 6, 1), ("eng", 2, 0)],
                str(audio_layout(out)))
            ratio = os.path.getsize(out) / (float(sc["size"]) * GIB)
            add("size <= target", ratio <= 1.0, f"{ratio:.3f} of the target")
            add("size >= 85 % of the target", ratio >= 0.85, f"{ratio:.3f} of the target")
            log = open(os.path.join(d, "log.txt"), encoding="utf-8", errors="replace").read()
            add("settings applied", "speed fast (preset veryfast), 720p at most, audio AAC 128 kbps per track, surround kept"
                in log, "see log.txt")
    elif name == "compress-constant-quality":
        no_errors()
        out = output(r"film_compressed\.mkv$")
        if out:
            add("codec h264, frames kept", streams(out, "video")[0]["codec_name"] == "h264"
                and frames(out) == frames(src), f"{frames(out)} vs {frames(src)}")
            add("both audio tracks, French first", audio_layout(out) == [("fre", 2, 1), ("eng", 2, 0)],
                str(audio_layout(out)))
            log = open(os.path.join(d, "log.txt"), encoding="utf-8", errors="replace").read()
            add("one pass at CRF 22, no size asked", "-crf 22" in log and "-pass" not in log
                and not [e for e in result["events"] if e[0] == "askstring"], "see log.txt")
            infos = [e[2] for e in result["events"] if e[0] == "showinfo"]
            add("the size of the file is told", infos and re.search(r"film_compressed\.mkv \([\d.]+ MB\)", infos[0]),
                infos[0] if infos else "")
    elif name == "compress-keep-original-audio":
        no_errors()
        out = output(r"film_compressed\.mkv$")
        if out:
            # The French 5.1 (second in the source) first, both tracks copied bit for bit
            add("French 5.1 first, English stereo", audio_layout(out) == [("fre", 6, 1), ("eng", 2, 0)],
                str(audio_layout(out)))
            add("audio copied, not re-encoded", stream_md5(out, "0:a:0") == stream_md5(src, "0:a:1")
                and stream_md5(out, "0:a:1") == stream_md5(src, "0:a:0"))
            ratio = os.path.getsize(out) / (float(sc["size"]) * GIB)
            add("size <= target (the real audio size counted)", ratio <= 1.0, f"{ratio:.3f} of the target")
            add("size >= 85 % of the target", ratio >= 0.85, f"{ratio:.3f} of the target")
    elif name == "compress-avi-copy-shortcut":
        no_errors()
        out = output(r"megamind_compressed\.mkv$")
        if out:
            add("streams copied", streams(out, "video")[0]["codec_name"] == "mpeg4", streams(out, "video")[0]["codec_name"])
            add("frames kept", frames(out) == frames(src), f"{frames(out)} vs {frames(src)}")
    elif name == "compress-batch-2-files":
        no_errors()
        film, bird = output(r"film_compressed\.mkv$"), output(r"cockatoo_compressed\.mkv$")
        if film and bird:
            add("film fits the target", os.path.getsize(film) <= float(sc["size"]) * GIB, f"{os.path.getsize(film) / GIB:.4f} GB")
            add("film has the added subtitles", any("Good morning" in t for t in subtitle_texts(film)))
            add("cockatoo copied (already small)", os.path.getsize(bird) <= os.path.getsize(os.path.join(d, "cockatoo.mp4")) * 1.02)
    elif name == "compress-invalid-sizes-then-too-small":
        messages = [e[2] for e in errors]
        add("2 invalid size errors", messages[:2] == ["Invalid size. Must be greater than 0."] * 2, str(messages[:2]))
        add("too small size explained", len(messages) == 3 and "smallest size for this video is" in messages[2],
            messages[-1] if messages else "")
        add("nothing written", not new, str(new))
    elif name == "compress-size-cancelled":
        add("nothing written", not new, str(new))
    elif name == "compress-no-file-chosen":
        add("error shown", [e[2] for e in errors] == ["No video files selected. Please choose at least one video file."],
            str(errors))
    elif name == "translate-real-google":
        if any("Google Translate stopped answering" in e[2] for e in errors):
            raise Skipped("Google Translate refuses the requests of this computer")
        no_errors()
        import pysrt
        out = output(r"film\.en_translated\.srt$")
        if out:
            before, after = pysrt.open(os.path.join(d, "film.en.srt")), pysrt.open(out)
            add("same entries and timings", [(s.start, s.end) for s in before] == [(s.start, s.end) for s in after])
            french = sum(bool(re.search(r"\b(le|la|les|un|une|des|du|de|est|nous|vous)\b", s.text, re.I)) for s in after)
            add("French text", french >= 0.7 * len(after), f"{french}/{len(after)} lines, e.g. {after[1].text!r}")
    elif name.startswith("translate-deepl"):
        no_errors()
        import pysrt
        subtitle = sc["subtitles"][0]
        out = output(re.escape(os.path.splitext(subtitle)[0]) + r"_translated\.srt$")
        if out:
            before, after = pysrt.open(os.path.join(d, subtitle)), pysrt.open(out)
            by_deepl = sum(b.text == f"[deepl] {a.text}" for a, b in zip(before, after))
            by_google = sum(b.text == f"[fr] {a.text}" for a, b in zip(before, after))
            add("same entries and timings", [(s.start, s.end) for s in before] == [(s.start, s.end) for s in after])
            infos = [e[2] for e in result["events"] if e[0] == "showinfo"]
            if name == "translate-deepl":
                add("every line translated by DeepL", by_deepl == len(before), f"{by_deepl}/{len(before)}")
            else:
                add("first batch by DeepL, the rest by Google", by_deepl == 50 and by_google == len(before) - 50,
                    f"DeepL {by_deepl}, Google {by_google} of {len(before)}")
                add("the user is told", infos and "translated with Google" in infos[0], infos[0] if infos else "")
            add("the key is not saved in the profile of the user", os.path.exists(os.path.join(d, "deepl_key.txt")))
    elif name.startswith("translate-") and name != "translate-not-a-subtitle":
        no_errors()
        import pysrt
        for subtitle in sc["subtitles"]:
            out = output(re.escape(os.path.splitext(subtitle)[0]) + r"_translated\.srt$")
            if out:
                before, after = pysrt.open(os.path.join(d, subtitle)), pysrt.open(out)
                add(f"{subtitle}: same entries and timings",
                    [(s.start, s.end) for s in before] == [(s.start, s.end) for s in after], f"{len(after)} entries")
                right = sum(b.text == f"[fr] {a.text}" for a, b in zip(before, after))
                add(f"{subtitle}: every line translated, in its place", right == len(before), f"{right}/{len(before)}")
    elif name == "translate-not-a-subtitle":
        add("error reported, nothing written", any(e[1] == "Translation Error" for e in errors) and not new, str(errors)[:200])
    elif name == "upscale-refused-at-the-disk-space-question":
        questions = [e for e in result["events"] if e[0] == "askyesno"]
        add("duration and temporary disk space announced", questions and "Estimated duration" in questions[0][2]
            and re.search(r"Temporary disk space: about [\d.]+ [MG]B", questions[0][2]), questions[0][2] if questions else "")
        add("nothing written", not [f for f in new if f.startswith("out")], str(new))
    elif name.startswith("upscale-"):
        no_errors()
        questions = [e for e in result["events"] if e[0] == "askyesno"]
        add("duration and temporary disk space announced", questions and questions[0][1] == "Upscaling"
            and "Estimated duration" in questions[0][2], questions[0][2] if questions else "")
        target = int(re.search(r"(\d+)p-", name).group(1))
        out = output(rf"_upscaled_{target}p\.mkv$")
        if out:
            video = streams(out, "video")[0]
            wanted = "hevc" if name.endswith("x265") else "h264"
            add(f"{target} lines", video["height"] == target, f"{video['width']}x{video['height']}")
            add(f"codec {wanted}", video["codec_name"] == wanted, video["codec_name"])
            # Same timeline: each frame at its time; a source starting after 0 gets its first frame repeated from 0
            source = streams(src, "video")[0]
            fps = Fraction(source["avg_frame_rate"])
            offset = round(float(source.get("start_time", 0)) * fps)
            add("same timeline (frames, time of the last one)", frames(out) == frames(src) + offset
                and abs(packet_times(out)[-1] - packet_times(src)[-1]) < 0.5 / fps,
                f"{frames(out)} = {frames(src)} + {offset}")
            add("audio kept", len(streams(out, "audio")) == len(streams(src, "audio")))
            add("no temporary file left", len([f for f in new if f.startswith("out")]) == 1, str(new))
    elif name.startswith("audio-conversion"):
        no_errors()
        codec = "opus" if "opus" in name else "aac"
        out = output(rf"_{codec}\.mkv$")
        if out:
            add(f"audio in {codec}", {s["codec_name"] for s in streams(out, "audio")} == {codec},
                str([s["codec_name"] for s in streams(out, "audio")]))
            add("video copied", frames(out) == frames(src) and streams(out, "video")[0]["codec_name"]
                == streams(src, "video")[0]["codec_name"])
            if name != "audio-conversion-divx-ac3-to-aac":
                wanted = [("fre", 6, 1), ("eng", 2, 0)] if "surround" in name else [("fre", 2, 1), ("eng", 2, 0)]
                add("French first, channels", audio_layout(out) == wanted, str(audio_layout(out)))
                add("subtitles kept", len(streams(out, "subtitle")) == 1)
            if "opus" in name:
                # The requested bitrates: Opus is VBR, and codes the synthetic noise of the test far below its target
                # (on real movie audio: 238 kbps for 256, 109 for 128)
                log = open(os.path.join(d, "log.txt"), encoding="utf-8", errors="replace").read()
                add("bitrate 128 kbps per stereo track, twice for 5.1", "-b:a:0 256k -b:a:1 128k" in log, "see log.txt")
    elif name.startswith("add-subtitles"):
        no_errors()
        if name in ("add-subtitles-soft", "add-subtitles-batch", "add-subtitles-avi"):
            stem = "megamind" if name == "add-subtitles-avi" else "film"
            out = output(rf"{stem}_with_subtitles\.mkv$")
            if out:
                add("subtitles added", any("Good morning" in t for t in subtitle_texts(out)))
                add("video copied", frames(out) == frames(os.path.join(d, sc["videos"][0])))
        if name in ("add-subtitles-hard", "add-subtitles-batch"):
            out = output(r"cockatoo_with_subtitles\.mp4$")
            if out:
                reference = os.path.join(d, "cockatoo.mp4")
                bottom, top = band_psnr(out, reference, "bottom"), band_psnr(out, reference, "top")
                add("subtitles burned", bottom < top - 3, f"bottom {bottom:.1f} dB, top {top:.1f} dB")
    elif name == "audio-tracks-keep-french":
        no_errors()
        out = output(r"film_audio_processed\.mkv$")
        if out:
            add("only the French track, default", audio_layout(out) == [("fre", 6, 1)], str(audio_layout(out)))
            add("video and subtitles kept", len(streams(out, "video")) == 1 and len(streams(out, "subtitle")) == 1)
    return c


# ---- runner

def driver_command(scenario_file):
    cmd = [sys.executable, os.path.join(HERE, "drive.py"), scenario_file]
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        if not shutil.which("xvfb-run"):
            sys.exit("No display: install xvfb (xvfb-run) or run the battery in a graphical session.")
        cmd = ["xvfb-run", "-a", *cmd]
    return cmd


def run_scenario(name, sc, inputs):
    d = os.path.join(WORK, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    if sc.get("upscale"):
        sys.path.insert(0, ROOT)
        from gui_upscale import REALESRGAN_EXE
        if not os.path.isfile(REALESRGAN_EXE):
            raise Skipped("Real-ESRGAN is not installed (python scripts/fetch_deps.py)")
    for f in sc["inputs"]:
        try:
            os.link(os.path.join(inputs, f), os.path.join(d, f))
        except OSError:
            shutil.copyfile(os.path.join(inputs, f), os.path.join(d, f))
    if "outdir" in sc:
        os.makedirs(os.path.join(d, sc["outdir"]))
    scenario = dict(sc, workdir=d, videos=[os.path.join(d, v) for v in sc.get("videos", [])],
                    subtitles=[os.path.join(d, s) for s in sc.get("subtitles", [])],
                    outdir=os.path.join(d, sc.get("outdir", "")))
    scenario_file = os.path.join(d, "scenario.json")
    with open(scenario_file, "w", encoding="utf-8") as f:
        json.dump(scenario, f)
    with open(os.path.join(d, "log.txt"), "w", encoding="utf-8") as log:
        try:
            # UTF-8 output: redirected to a file, Python on Windows would write cp1252 and fail on the emojis.
            # No DeepL key of the user: only the scenarios that give one use DeepL
            env = {name: value for name, value in os.environ.items() if name != "DEEPL_API_KEY"}
            env.update(PYTHONIOENCODING="utf-8", **sc.get("env", {}))
            subprocess.run(driver_command(scenario_file), stdout=log, stderr=subprocess.STDOUT,
                           env=env, timeout=3600 if sc.get("upscale") else 900)
        except subprocess.TimeoutExpired:
            pass
    try:
        with open(os.path.join(d, "result.json"), encoding="utf-8") as f:
            result = json.load(f)
    except FileNotFoundError:
        result = {"events": [], "error": "no result: the scenario crashed or timed out (see log.txt)", "unused_steps": []}
    new = sorted(os.path.relpath(os.path.join(folder, f), d).replace(os.sep, "/") for folder, _, files in os.walk(d)
                 for f in files if f not in sc["inputs"] and f not in ("scenario.json", "result.json", "log.txt"))
    return check(name, sc, d, result, new)


def main(args):
    if "--list" in args:
        print("\n".join(SCENARIOS))
        return 0
    names = [n for n in SCENARIOS if not args or any(n.startswith(prefix) for prefix in args)]
    if not names:
        sys.exit(f"No scenario starts with {' or '.join(args)} (see --list)")
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} must be installed and in the PATH.")
    inputs = media.build()
    report, counts = {}, {"OK": 0, "FAILED": 0, "SKIPPED": 0}
    for name in names:
        print(f"=== {name}", flush=True)
        start = time.time()
        try:
            checks = run_scenario(name, SCENARIOS[name], inputs)
            status = "OK" if all(passed for _, passed, _ in checks) else "FAILED"
        except Skipped as e:
            checks, status = [(f"skipped: {e}", True, "")], "SKIPPED"
        except Exception as e:  # a check that cannot even run is a failure, the other scenarios go on
            checks, status = [("checks ran", False, f"{type(e).__name__}: {e}")], "FAILED"
        counts[status] += 1
        report[name] = {"status": status, "seconds": round(time.time() - start, 1), "checks": checks}
        for what, passed, detail in checks:
            print(f"  {'PASS' if passed else 'FAIL'} {what}" + (f" ({detail})" if detail and not passed else ""))
        print(f"  -> {status} in {time.time() - start:.0f} s", flush=True)
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\n{counts['OK']} OK, {counts['FAILED']} FAILED, {counts['SKIPPED']} SKIPPED"
          f" (details in {os.path.join(WORK, '<scenario>', 'log.txt')})")
    return 1 if counts["FAILED"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
