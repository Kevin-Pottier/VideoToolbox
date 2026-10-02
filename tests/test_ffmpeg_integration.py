"""End-to-end tests running the real ffmpeg on small generated videos (skipped when FFmpeg is missing)."""
import os
import subprocess
import sys
import threading
import time

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
    subtitles = streams_of_type(out, "subtitle")
    assert [(s["codec_name"], s.get("tags", {}).get("language")) for s in subtitles] == [("subrip", None), ("subrip", "eng")]
    assert [s["disposition"]["default"] for s in subtitles] == [1, 0]
    assert "Léa : « ça va » €" in subtitle_text(out, 0)  # the added file, then the subtitles of the source
    assert len(streams_of_type(out, "attachment")) == 1


@pytest.fixture
def bilingual_mkv(tmp_path):
    """Detailed (big) video with the English audio first and default, the French one second, English subtitles."""
    (tmp_path / "eng.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    path = tmp_path / "bilingual.mkv"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=2,noise=alls=30:allf=t",
               *lavfi_audio(duration=2), *lavfi_audio(duration=2, frequency=600), "-i", str(tmp_path / "eng.srt"),
               *(arg for i in range(4) for arg in ("-map", str(i))), "-c:v", "libx264", "-crf", "10", "-c:a", "aac",
               "-c:s", "srt", "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=fre",
               "-disposition:a:0", "default", "-disposition:a:1", "0", str(path))
    return str(path)


@pytest.mark.parametrize("ext, target_gb, encoded", [("mp4", 0.0003, True), ("mkv", 0.01, False)])
def test_compression_keeps_every_audio_track_with_french_first(bilingual_mkv, ext, target_gb, encoded):
    # Encoded (target smaller than the file) or copied, without subtitle option: the French track used to be dropped
    import compression
    compression.run_compression(bilingual_mkv, "none", None, ext, target_gb, gui_progress=noop)

    out = bilingual_mkv.replace(".mkv", f"_compressed.{ext}")
    audio = streams_of_type(out, "audio")
    assert [(s["tags"]["language"], s["disposition"]["default"]) for s in audio] == [("fre", 1), ("eng", 0)]
    assert (stream_md5(out, "0:v") != stream_md5(bilingual_mkv, "0:v")) == encoded
    assert "Hello" in subtitle_text(out, 0)


def test_two_pass_compression_of_an_mkv_to_mp4_hits_the_target_size(tmp_path, monkeypatch):
    # AAC in MKV starts before 0: in MP4 the second pass would duplicate a frame without passthrough timestamps
    import compression
    monkeypatch.setattr(compression, "STALL_TIMEOUT", 60)  # fail fast instead of hanging if x264 gets stuck
    src = tmp_path / "noisy.mkv"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=6,noise=alls=30:allf=t", *lavfi_audio(duration=6),
               "-c:v", "libx264", "-crf", "10", "-c:a", "aac", str(src))
    target_gb = 0.00085  # about 1000 kbps of video

    compression.run_compression(str(src), "none", None, "mp4", target_gb, gui_progress=noop)

    out = tmp_path / "noisy_compressed.mp4"
    assert count_frames(out) == count_frames(src)  # a complete video, not the leftover of a failed pass
    assert 0.85 < os.path.getsize(out) / (target_gb * 1024 ** 3) <= 1.0


def test_failed_compression_leaves_no_output(movie_mkv, monkeypatch):
    import compression
    failing = ["ffmpeg", "-v", "error", "-i", "missing input.mkv", "out.mp4"]
    monkeypatch.setattr(compression, "build_copy_command", lambda *args, **kwargs: failing)
    monkeypatch.setattr(compression, "build_encode_commands", lambda *args, **kwargs: [(failing, 1.0)])
    output = movie_mkv.replace(".mkv", "_compressed.mp4")
    open(output, "wb").close()  # as if ffmpeg had started writing it
    with pytest.raises(compression.CompressionError, match="missing input.mkv"):
        compression.run_compression(movie_mkv, "none", None, "mp4", 0.01, gui_progress=noop)
    assert not os.path.exists(output)


def test_compression_aborts_when_the_target_size_is_too_small(movie_mkv):
    # The reason reaches the user (it used to be printed in the console only), with the smallest possible size
    from compression import CompressionError, run_compression
    with pytest.raises(CompressionError, match=r"(?s)Target size too small: only 0 kbps.*smallest size for this video is 0\.001 GB"):
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
"""Stand-in for realesrgan-ncnn-vulkan: scales every frame of -i into -o (same name, -f format)."""
import os, subprocess, sys
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
if os.environ.get("FAKE_REALESRGAN_FAIL"):
    sys.exit("vkCreateInstance failed")
for name in sorted(os.listdir(args["-i"])):
    out = os.path.join(args["-o"], os.path.splitext(name)[0] + "." + args["-f"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(args["-i"], name), "-q:v", "2",
                    "-vf", "scale=iw*{{0}}:ih*{{0}}".format(args["-s"]), out], check=True)
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


def test_ffprobe_streams_reports_an_unreadable_file(tmp_path):
    import audio_tracks
    bad = tmp_path / "not a video.mkv"
    bad.write_bytes(b"garbage")
    with pytest.raises(RuntimeError, match="ffprobe failed: .+"):
        audio_tracks.ffprobe_streams(str(bad))


def test_ffprobe_streams_reads_utf8_titles_and_frame_rates(tmp_path):
    # "Á" is encoded as C3 81 in UTF-8: 0x81 is undefined in Windows-1252
    import audio_tracks
    src = tmp_path / "titles.mkv"
    run_ffmpeg(*lavfi_video(rate="24000/1001"), *lavfi_audio(), "-map", "0", "-map", "1",
               "-c:v", "libx264", "-c:a", "aac", "-metadata:s:a:0", "title=Á la française", str(src))
    info = audio_tracks.ffprobe_streams(str(src))
    assert info.audio_tracks[0].title == "Á la française"
    assert info.video_tracks[0].avg_frame_rate == "24000/1001"
    assert info.duration == pytest.approx(1, abs=0.1)


def stream_md5(path, spec):
    """MD5 of the packets of a stream: identical when the stream was copied, not re-encoded."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", spec, "-c", "copy", "-f", "md5", "-"],
                         capture_output=True, text=True, check=True).stdout
    return out.strip()


@pytest.mark.parametrize("encoder_name, codec", [("libx265", "hevc"), ("libsvtav1", "av1")])
def test_compression_with_the_other_cpu_encoders(tmp_path, monkeypatch, encoder_name, codec):
    import compression
    import encoders
    if encoder_name not in encoders._built_encoders():
        pytest.skip(f"{encoder_name} is not in this FFmpeg build")
    monkeypatch.setattr(compression, "STALL_TIMEOUT", 60)
    src = tmp_path / "noisy.mkv"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=4,noise=alls=30:allf=t", *lavfi_audio(duration=4),
               "-c:v", "libx264", "-crf", "10", "-c:a", "aac", str(src))
    target_gb = 0.0006

    compression.run_compression(str(src), "none", None, "mp4", target_gb, gui_progress=noop,
                                encoder=encoders.BY_NAME[encoder_name])

    out = tmp_path / "noisy_compressed.mp4"
    assert [s["codec_name"] for s in streams_of_type(out, "video")] == [codec]
    assert count_frames(out) == count_frames(src)
    # Two passes hit the size; a single pass (SVT-AV1, GPU) only approaches it, here on a short and very noisy clip
    tolerance = 1.0 if encoders.BY_NAME[encoder_name].two_pass else 1.1
    assert os.path.getsize(out) <= target_gb * 1024 ** 3 * tolerance


def test_a_file_already_under_the_target_size_is_copied(movie_mkv):
    import compression
    compression.run_compression(movie_mkv, "none", None, "mkv", 0.01, gui_progress=noop)
    out = movie_mkv.replace(".mkv", "_compressed.mkv")
    assert stream_md5(out, "0:v") == stream_md5(movie_mkv, "0:v")  # not re-encoded
    assert [s["codec_name"] for s in streams_of_type(out, "subtitle")] == ["subrip"]


def test_copy_falls_back_to_encoding_when_the_container_refuses_a_codec(tmp_path, monkeypatch):
    # WMA audio cannot be copied into MP4: the file is encoded instead
    import compression
    src = tmp_path / "wma.mkv"
    run_ffmpeg(*lavfi_video(), *lavfi_audio(), "-map", "0", "-map", "1", "-c:v", "libx264", "-c:a", "wmav2", str(src))
    bitrates = []
    build = compression.build_encode_commands
    monkeypatch.setattr(compression, "build_encode_commands",
                        lambda *args, **kwargs: bitrates.append(args[3]) or build(*args, **kwargs))
    compression.run_compression(str(src), "none", None, "mp4", 0.01, gui_progress=noop)
    out = tmp_path / "wma_compressed.mp4"
    assert [s["codec_name"] for s in streams_of_type(out, "audio")] == ["aac"]
    assert count_frames(out) == count_frames(src)
    # About the bitrate of the source, not the whole budget (about 84000 kbps): the file was already small
    assert bitrates and bitrates[0] < 1000


@pytest.fixture
def xvid_avi(tmp_path):
    """AVI as made by DivX/XviD: MPEG-4 with B-frames, whose packets have no timestamp in AVI."""
    path = tmp_path / "divx.avi"
    run_ffmpeg(*lavfi_video(), *lavfi_audio(), "-c:v", "mpeg4", "-bf", "2", "-vtag", "XVID", "-c:a", "ac3", str(path))
    return str(path)


def test_avi_streams_are_copied_into_mkv(xvid_avi, tmp_path, awkward_subtitle):
    # The copies failed with "Can't write packet with unknown timestamp" (and left a broken file)
    import audio_tracks
    import compression
    from gui_add_subtitles import add_subtitles_to_video
    out = add_subtitles_to_video(xvid_avi, "soft", awkward_subtitle)
    assert out.endswith(".mkv") and count_frames(out) == count_frames(xvid_avi)

    info = audio_tracks.ffprobe_streams(xvid_avi)
    mapping = audio_tracks.build_audio_mapping_options(info, audio_tracks.AudioProcessingOptions(keep_all_audio=True))
    tracks = str(tmp_path / "tracks.mkv")
    subprocess.run(audio_tracks.build_ffmpeg_command(xvid_avi, tracks, mapping), check=True, capture_output=True)
    assert count_frames(tracks) == count_frames(xvid_avi)

    out = compression.run_compression(xvid_avi, "none", None, "mkv", 0.01, gui_progress=noop)
    assert stream_md5(out, "0:v") == stream_md5(xvid_avi, "0:v")  # copied, not re-encoded


def test_a_failed_subtitle_addition_leaves_no_output(movie_mkv, awkward_subtitle, monkeypatch):
    import gui_add_subtitles

    def failing_ffmpeg(cmd, *args):
        open(cmd[-2], "wb").close()  # as if ffmpeg had started writing the output (before "-y")
        return 1
    monkeypatch.setattr(gui_add_subtitles, "_run_with_progress", failing_ffmpeg)
    assert gui_add_subtitles.add_subtitles_to_video(movie_mkv, "soft", awkward_subtitle) is None
    assert not os.path.exists(movie_mkv.replace(".mkv", "_with_subtitles.mkv"))


def anamorphic_clip(tmp_path, seconds=1):
    src = tmp_path / "clip.mkv"
    run_ffmpeg(*lavfi_video(duration=seconds, size="32x18", rate="24000/1001"), *lavfi_audio(duration=seconds),
               "-vf", "setsar=4/3", "-c:v", "libx264", "-c:a", "flac", str(src))
    return src


@pytest.mark.skipif(sys.platform == "win32", reason="the fake Real-ESRGAN is a Python script with a shebang")
def test_upscale_pipeline_with_several_chunks_and_the_animation_model(tmp_path, fake_realesrgan, monkeypatch):
    gui_upscale = fake_realesrgan
    monkeypatch.setattr(gui_upscale, "chunk_frames", lambda *args: 7)  # 24 frames -> 4 chunks
    src = anamorphic_clip(tmp_path)
    outdir = tmp_path / "out"
    outdir.mkdir()
    progress = []
    anime = next(m for m in gui_upscale.MODELS if m.name == "realesr-animevideov3")

    out = gui_upscale.upscale_video(str(src), gui_upscale.probe_video(str(src)), 36, str(outdir),
                                    lambda *msg: progress.append(msg), threading.Event(), anime)

    assert count_frames(out) == count_frames(src)
    video = streams_of_type(out, "video")[0]
    assert (video["height"], video["avg_frame_rate"]) == (36, "24000/1001")
    assert ("progress", count_frames(src)) in progress
    assert any("x2 with realesr-animevideov3" in msg[1] for msg in progress if msg[0] == "stage")  # 18 -> 36: x2
    assert os.listdir(outdir) == [os.path.basename(out)]


@pytest.mark.skipif(sys.platform == "win32", reason="the fake Real-ESRGAN is a Python script with a shebang")
def test_upscale_with_another_encoder(tmp_path, fake_realesrgan):
    import encoders
    if "libx265" not in encoders._built_encoders():
        pytest.skip("libx265 is not in this FFmpeg build")
    gui_upscale = fake_realesrgan
    src = anamorphic_clip(tmp_path)
    outdir = tmp_path / "out"
    outdir.mkdir()
    out = gui_upscale.upscale_video(str(src), gui_upscale.probe_video(str(src)), 72, str(outdir), noop,
                                    threading.Event(), gui_upscale.MODELS[0], encoders.BY_NAME["libx265"])
    assert [s["codec_name"] for s in streams_of_type(out, "video")] == ["hevc"]
    assert count_frames(out) == count_frames(src)


@pytest.mark.skipif(sys.platform == "win32", reason="the fake Real-ESRGAN is a Python script with a shebang")
def test_a_realesrgan_failure_is_reported_and_leaves_nothing(tmp_path, fake_realesrgan, monkeypatch):
    gui_upscale = fake_realesrgan
    monkeypatch.setenv("FAKE_REALESRGAN_FAIL", "1")
    src = anamorphic_clip(tmp_path)
    outdir = tmp_path / "out"
    outdir.mkdir()
    with pytest.raises(gui_upscale.UpscaleError, match="Real-ESRGAN failed"):
        gui_upscale.upscale_video(str(src), gui_upscale.probe_video(str(src)), 72, str(outdir), noop, threading.Event())
    assert os.listdir(outdir) == []


@pytest.mark.skipif(sys.platform == "win32", reason="the fake Real-ESRGAN is a Python script with a shebang")
def test_cancelling_in_the_middle_of_the_pipeline_stops_every_process(tmp_path, fake_realesrgan, monkeypatch):
    gui_upscale = fake_realesrgan
    monkeypatch.setattr(gui_upscale, "chunk_frames", lambda *args: 5)
    src = anamorphic_clip(tmp_path, seconds=4)
    outdir = tmp_path / "out"
    outdir.mkdir()
    cancel = threading.Event()

    def report(kind, *args):
        if kind == "progress" and args[0] >= 5:  # first chunk upscaled
            cancel.set()

    start = time.time()
    with pytest.raises(gui_upscale.UpscaleCancelled):
        gui_upscale.upscale_video(str(src), gui_upscale.probe_video(str(src)), 72, str(outdir), report, cancel)
    assert time.time() - start < 30
    assert os.listdir(outdir) == []


@pytest.fixture
def hd_surround(tmp_path):
    """720p video with a 5.1(side) track, as in DTS/AC3 movies (light grain: heavy noise at every frame cannot
    be compressed to the target, whatever the encoder)."""
    path = tmp_path / "hd.mkv"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=2,noise=alls=4:allf=t",
               "-f", "lavfi", "-i", "anoisesrc=d=2:amplitude=0.1,aformat=channel_layouts=5.1(side)",
               "-c:v", "libx264", "-crf", "18", "-c:a", "ac3", str(path))
    return str(path)


def test_compression_settings_resolution_speed_and_surround(hd_surround):
    import compression
    settings = compression.CompressionSettings(speed="fast", max_height=480, audio_kbps=96, keep_surround=True)
    out = compression.run_compression(hd_surround, "none", None, "mp4", 0.0004, gui_progress=noop, settings=settings)

    video = streams_of_type(out, "video")[0]
    assert (video["width"], video["height"]) == (854, 480)
    assert count_frames(out) == count_frames(hd_surround)
    [audio] = streams_of_type(out, "audio")
    assert (audio["channels"], audio["channel_layout"]) == (6, "5.1")  # 5.1(side) mapped to the standard layout
    assert os.path.getsize(out) <= 0.0004 * 1024 ** 3


def test_a_small_file_reduced_in_resolution_is_encoded_but_not_bigger(hd_surround):
    # Under the target, the copy shortcut cannot reduce the resolution: the file is encoded, at the bitrate
    # of the source at most (not the whole budget, about 40 Mbps here)
    import compression
    settings = compression.CompressionSettings(max_height=480, audio_kbps=96)
    out = compression.run_compression(hd_surround, "none", None, "mkv", 0.01, gui_progress=noop, settings=settings)

    assert streams_of_type(out, "video")[0]["height"] == 480
    assert streams_of_type(out, "audio")[0]["channels"] == 2  # stereo by default
    assert os.path.getsize(out) <= os.path.getsize(hd_surround) * 1.1
