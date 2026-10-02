import pytest

import audio_codecs
from audio_codecs import AudioSettings
from audio_conversion import build_conversion_command, output_path
from audio_tracks import AudioTrackInfo, MediaFileInfo, SubtitleTrackInfo


def movie():
    return MediaFileInfo(file_path="in.mkv", audio_tracks=[
        AudioTrackInfo(1, "eng", title="VO", channels=6, is_default=True, disposition_flags=["comment"]),
        AudioTrackInfo(2, "ger", channels=2),
        AudioTrackInfo(3, "fre", title="VFF", channels=6, disposition_flags=["dub"]),
        AudioTrackInfo(4, None, title="VFQ 2.0", channels=2),
        AudioTrackInfo(5, "fre", title="Audiodescription", channels=2, disposition_flags=["visual_impaired"]),
    ])


def maps_of(cmd):
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]


def dispositions_of(cmd):
    return {arg: cmd[i + 1] for i, arg in enumerate(cmd) if arg.startswith("-disposition")}


def option(cmd, name):
    return cmd[cmd.index(name) + 1]


def test_every_audio_track_is_kept_with_the_french_ones_first():
    cmd, tracks, has_french = build_conversion_command("in.mkv", "out.mkv", movie())
    assert has_french
    assert [t.stream_index for t in tracks] == [3, 4, 5, 1, 2]
    assert maps_of(cmd) == ["0:v?", "0:3", "0:4", "0:5", "0:1", "0:2", "0:s?", "0:t?"]


def test_first_french_track_becomes_default_and_other_flags_are_kept():
    cmd, _, _ = build_conversion_command("in.mkv", "out.mkv", movie())
    # Only the tracks whose default flag changes get a -disposition (it replaces every flag)
    assert dispositions_of(cmd) == {"-disposition:a:0": "default+dub", "-disposition:a:3": "comment"}


def test_default_settings_are_the_former_audio_fix():
    # AAC stereo at 160 kbps, the video and the subtitles copied
    cmd, _, _ = build_conversion_command("in.mkv", "out.mkv", movie())
    assert option(cmd, "-c") == "copy"
    for name, value in (("-c:a", "aac"), ("-ac", "2"), ("-ar", "48000"), ("-b:a:0", "160k"), ("-b:a:4", "160k")):
        assert option(cmd, name) == value


@pytest.mark.parametrize("codec, encoder, layouts", [
    ("aac", "aac", "mono|stereo|5.1|7.1"),
    ("opus", "libopus", "mono|stereo|5.1|7.1"),  # libopus refuses the 5.1(side) of DTS/AC3 tracks
    ("ac3", "ac3", "mono|stereo|5.1"),            # a 7.1 track would become 5.0, without its LFE
    ("eac3", "eac3", "mono|stereo|5.1"),
])
def test_surround_kept_at_twice_the_bitrate_in_layouts_the_codec_takes(codec, encoder, layouts):
    cmd, _, _ = build_conversion_command("in.mkv", "out.mkv", movie(), AudioSettings(codec, 128, keep_surround=True))
    assert option(cmd, "-c:a") == encoder and "-ac" not in cmd
    assert option(cmd, "-af") == f"aformat=channel_layouts={layouts}"
    # Output order: VFF 5.1, VFQ 2.0, AD 2.0, VO 5.1, GER 2.0
    assert [option(cmd, f"-b:a:{i}") for i in range(5)] == ["256k", "128k", "128k", "256k", "128k"]


def test_flac_is_lossless_without_bitrate_nor_resampling():
    cmd, _, _ = build_conversion_command("in.mkv", "out.mkv", movie(), AudioSettings("flac", 128, keep_surround=True))
    assert option(cmd, "-c:a") == "flac"
    assert not [arg for arg in cmd if arg.startswith("-b:a") or arg in ("-ar", "-af")]


@pytest.mark.parametrize("source, codec, output", [
    ("film.mkv", "aac", "film_aac.mkv"),
    ("film.mp4", "opus", "film_opus.mp4"),
    ("film.MOV", "ac3", "film_ac3.mov"),
    ("film.mp4", "flac", "film_flac.mkv"),  # FLAC in MP4: old ffmpeg versions and Apple players refuse it
    ("film.avi", "aac", "film_aac.mkv"),    # AVI cannot store AAC properly, nor subtitles
])
def test_output_name_and_container(tmp_path, source, codec, output):
    assert output_path(str(tmp_path / source), AudioSettings(codec)) == str(tmp_path / output)


def test_mp4_subtitles_become_srt_in_mkv_and_mp4_has_no_attachments():
    media = MediaFileInfo("in.mp4", audio_tracks=[AudioTrackInfo(1, "fre")],
                          subtitle_tracks=[SubtitleTrackInfo(2, "fre", codec="mov_text")])
    to_mkv, _, _ = build_conversion_command("in.mp4", "out.mkv", media, AudioSettings("flac"))
    assert option(to_mkv, "-c:s:0") == "srt" and "0:t?" in maps_of(to_mkv)
    to_mp4, _, _ = build_conversion_command("in.mp4", "out.mp4", media)
    assert "-c:s:0" not in to_mp4 and "0:t?" not in maps_of(to_mp4) and option(to_mp4, "-movflags") == "+faststart"


def test_without_french_track_the_order_and_flags_are_unchanged():
    media = MediaFileInfo(file_path="in.mkv", audio_tracks=[
        AudioTrackInfo(1, "eng", is_default=True), AudioTrackInfo(2, "ger")])
    cmd, tracks, has_french = build_conversion_command("in.mkv", "out.mkv", media)
    assert not has_french
    assert [t.stream_index for t in tracks] == [1, 2]
    assert dispositions_of(cmd) == {}


def test_only_the_codecs_of_this_ffmpeg_build_are_offered(monkeypatch):
    monkeypatch.setattr(audio_codecs, "_built_audio_encoders", lambda: {"aac", "ac3", "flac", "mp3"})
    audio_codecs.available_codecs.cache_clear()
    try:
        assert [codec.name for codec in audio_codecs.available_codecs()] == ["aac", "ac3", "flac"]
    finally:
        audio_codecs.available_codecs.cache_clear()
