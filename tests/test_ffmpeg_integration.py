"""End-to-end tests running the real ffmpeg on small generated videos (skipped when FFmpeg is missing)."""
import os
import subprocess
import sys
import threading

import pytest

from helpers import (count_frames, lavfi_audio, lavfi_video, probe, requires_ffmpeg, run_ffmpeg, streams_of_type,
                     subtitle_text)

pytestmark = requires_ffmpeg

FRENCH_SRT = "1\r\n00:00:00,000 --> 00:00:01,000\r\nLéa : « ça va » €\r\n"


def noop(*args):
    pass


@pytest.fixture
def awkward_subtitle(tmp_path):
    """Windows-1252 subtitle in another folder, with a name that breaks naive ffmpeg filter arguments."""
    folder = tmp_path / "autre dossier"
    folder.mkdir()
    path = folder / "Sous-titres l'été, [VF].srt"
    path.write_bytes(FRENCH_SRT.encode("cp1252"))
    return str(path)


@pytest.fixture
def movie_mkv(tmp_path):
    """MKV with one audio track, an English subtitle track and an attached font."""
    (tmp_path / "eng.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    (tmp_path / "font.ttf").write_bytes(b"not a real font")
    path = tmp_path / "movie.mkv"
    run_ffmpeg(*lavfi_video(), *lavfi_audio(), "-i", str(tmp_path / "eng.srt"),
               "-map", "0", "-map", "1", "-map", "2", "-c:v", "libx264", "-c:a", "aac", "-c:s", "srt",
               "-metadata:s:s:0", "language=eng",
               "-attach", str(tmp_path / "font.ttf"), "-metadata:s:t", "mimetype=application/x-truetype-font",
               str(path))
    return str(path)


def test_audio_fix_keeps_every_track_with_french_first(tmp_path):
    from audio_fix import run_audio_fix
    (tmp_path / "fr.srt").write_text(FRENCH_SRT, encoding="utf-8")
    src = tmp_path / "multi.mkv"
    run_ffmpeg(*lavfi_video(), *(arg for f in (440, 500, 600, 700, 800) for arg in lavfi_audio(frequency=f)),
               "-i", str(tmp_path / "fr.srt"),
               *(arg for i in range(7) for arg in ("-map", str(i))),
               "-c:v", "libx264", "-c:a", "aac", "-ac:a:0", "6", "-c:s", "srt",
               "-metadata:s:a:0", "language=eng", "-metadata:s:a:0", "title=VO",
               "-metadata:s:a:1", "language=ger",
               "-metadata:s:a:2", "language=fre", "-metadata:s:a:2", "title=VFF",
               "-metadata:s:a:3", "title=VFQ 2.0",
               "-metadata:s:a:4", "language=fre", "-metadata:s:a:4", "title=Audiodescription",
               "-disposition:a:0", "default", "-disposition:a:1", "0", "-disposition:a:2", "0",
               "-disposition:a:3", "0", "-disposition:a:4", "visual_impaired",
               str(src))

    order = run_audio_fix(str(src), gui_progress=noop)

    out = tmp_path / "multi_fixed.mkv"
    audio = streams_of_type(out, "audio")
    assert order == ["FRE 1ch (VFF)", "? 1ch (VFQ 2.0)", "FRE 1ch (Audiodescription)", "ENG 6ch (VO)", "GER 1ch"]
    assert [s.get("tags", {}).get("title") for s in audio] == ["VFF", "VFQ 2.0", "Audiodescription", "VO", None]
    assert [s["disposition"]["default"] for s in audio] == [1, 0, 0, 0, 0]
    assert audio[2]["disposition"]["visual_impaired"] == 1
    assert {(s["codec_name"], s["channels"]) for s in audio} == {("aac", 2)}
    assert len(streams_of_type(out, "subtitle")) == 1


def test_add_soft_subtitles_keeps_existing_tracks(movie_mkv, awkward_subtitle):
    from gui_add_subtitles import add_subtitles_to_video
    out = add_subtitles_to_video(movie_mkv, "soft", awkward_subtitle)

    assert out and os.path.exists(out)
    subtitles = streams_of_type(out, "subtitle")
    assert [s.get("tags", {}).get("language") for s in subtitles] == ["eng", None]
    assert "Léa : « ça va » €" in subtitle_text(out, 1)  # converted from Windows-1252
    assert len(streams_of_type(out, "attachment")) == 1


def test_add_soft_subtitles_to_mp4_without_audio(tmp_path, awkward_subtitle):
    from gui_add_subtitles import add_subtitles_to_video
    src = tmp_path / "silent.mp4"
    run_ffmpeg(*lavfi_video(), "-c:v", "libx264", str(src))

    out = add_subtitles_to_video(str(src), "soft", awkward_subtitle)

    assert [s["codec_name"] for s in streams_of_type(out, "subtitle")] == ["mov_text"]


def test_burn_subtitles_with_an_awkward_file_name(movie_mkv, awkward_subtitle):
    from gui_add_subtitles import add_subtitles_to_video
    out = add_subtitles_to_video(movie_mkv, "hard", awkward_subtitle)
    assert out and os.path.exists(out)


def test_compression_with_soft_subtitles_in_mkv(movie_mkv, awkward_subtitle):
    from compression import run_compression
    run_compression(movie_mkv, "soft", awkward_subtitle, "mkv", 0.002, gui_progress=noop)

    out = movie_mkv.replace(".mkv", "_compressed.mkv")
    assert [s["codec_name"] for s in streams_of_type(out, "subtitle")] == ["subrip"]
    assert "Léa : « ça va » €" in subtitle_text(out, 0)


def test_compression_aborts_when_the_target_size_is_too_small(movie_mkv):
    from compression import run_compression
    run_compression(movie_mkv, "none", None, "mp4", 0.00001, gui_progress=noop)
    assert not os.path.exists(movie_mkv.replace(".mkv", "_compressed.mp4"))


def test_audio_tracks_to_mp4_converts_text_subtitles(tmp_path):
    import audio_tracks
    (tmp_path / "en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    src = tmp_path / "subs.mkv"
    run_ffmpeg(*lavfi_video(), *lavfi_audio(), "-i", str(tmp_path / "en.srt"),
               "-map", "0", "-map", "1", "-map", "2", "-c:v", "libx264", "-c:a", "aac", "-c:s", "srt", str(src))
    info = audio_tracks.ffprobe_streams(str(src))
    mapping = audio_tracks.build_audio_mapping_options(info, audio_tracks.AudioProcessingOptions(keep_all_audio=True))
    out = tmp_path / "out.mp4"

    subprocess.run(audio_tracks.build_ffmpeg_command(str(src), str(out), mapping), capture_output=True, check=True)

    assert [s["codec_name"] for s in streams_of_type(out, "subtitle")] == ["mov_text"]


def test_probe_video_reads_size_rate_and_duration(tmp_path):
    import gui_upscale
    src = tmp_path / "ntsc.mkv"
    run_ffmpeg(*lavfi_video(duration=2, size="64x36", rate="24000/1001"), "-c:v", "libx264", str(src))
    info = gui_upscale.probe_video(str(src))
    assert (info["width"], info["height"], info["fps"]) == (64, 36, "24000/1001")
    assert info["duration"] == pytest.approx(2, abs=0.1)


FAKE_REALESRGAN = '''#!{python}
"""Stand-in for realesrgan-ncnn-vulkan: scales every frame of -i into -o, keeping the file names."""
import os, subprocess, sys
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
for name in sorted(os.listdir(args["-i"])):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(args["-i"], name),
                    "-vf", "scale=iw*{{0}}:ih*{{0}}".format(args["-s"]), os.path.join(args["-o"], name)], check=True)
'''


@pytest.fixture
def fake_realesrgan(tmp_path, monkeypatch):
    import gui_upscale
    exe = tmp_path / "fake-realesrgan"
    exe.write_text(FAKE_REALESRGAN.format(python=sys.executable), encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setattr(gui_upscale, "REALESRGAN_EXE", str(exe))
    return gui_upscale


@pytest.mark.skipif(sys.platform == "win32", reason="the fake Real-ESRGAN is a Python script with a shebang")
def test_upscale_keeps_frame_count_rate_duration_and_audio(tmp_path, fake_realesrgan):
    gui_upscale = fake_realesrgan
    src = tmp_path / "clip.mkv"
    # Anamorphic 32x18 with a 4:3 sample aspect ratio (displayed as 42x18) at 23.976 fps
    run_ffmpeg(*lavfi_video(duration=1, size="32x18", rate="24000/1001"), *lavfi_audio(duration=1),
               "-vf", "setsar=4/3", "-c:v", "libx264", "-c:a", "flac", str(src))
    outdir = tmp_path / "out"
    outdir.mkdir()
    info = gui_upscale.probe_video(str(src))

    out = gui_upscale.upscale_video(str(src), info, 720, str(outdir), noop, threading.Event())

    video = streams_of_type(out, "video")[0]
    assert (video["height"], video["avg_frame_rate"], video["sample_aspect_ratio"]) == (720, "24000/1001", "1:1")
    assert video["width"] == 1680  # square pixels: 42x18 scaled to 720 lines
    assert count_frames(out) == count_frames(src)
    assert float(probe(out)["format"]["duration"]) == pytest.approx(float(probe(src)["format"]["duration"]), abs=0.05)
    assert [s["codec_name"] for s in streams_of_type(out, "audio")] == ["flac"]
    assert os.listdir(outdir) == [os.path.basename(out)]  # temporary frames removed


@pytest.mark.skipif(sys.platform == "win32", reason="the fake Real-ESRGAN is a Python script with a shebang")
def test_cancelled_upscale_leaves_no_file(tmp_path, fake_realesrgan):
    gui_upscale = fake_realesrgan
    src = tmp_path / "clip.mp4"
    run_ffmpeg(*lavfi_video(duration=1), "-c:v", "libx264", str(src))
    outdir = tmp_path / "out"
    outdir.mkdir()
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(gui_upscale.UpscaleCancelled):
        gui_upscale.upscale_video(str(src), gui_upscale.probe_video(str(src)), 720, str(outdir), noop, cancel)
    assert os.listdir(outdir) == []
