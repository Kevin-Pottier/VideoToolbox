import pytest

from audio_tracks import (
    AudioProcessingOptions,
    AudioTrackInfo,
    MediaFileInfo,
    SubtitleTrackInfo,
    VideoTrackInfo,
    build_audio_mapping_options,
    build_ffmpeg_command,
    french_first,
    is_french_track,
)


@pytest.mark.parametrize("language, title, expected", [
    ("fre", None, True),
    ("fra", None, True),
    ("fr", None, True),
    ("fr-CA", None, True),
    ("FRE", None, True),
    ("eng", "VFF", False),  # the language tag wins over the title
    (None, "VFF 5.1", True),
    ("und", "VFQ", True),
    (None, "French", True),
    (None, "Français", True),
    (None, "TrueFrench", True),
    (None, "FR 2.0", True),
    (None, "VOSTFR", False),  # original version with French subtitles
    (None, "VO", False),
    (None, None, False),
    ("und", None, False),
    ("eng", None, False),
])
def test_is_french_track(language, title, expected):
    assert is_french_track(AudioTrackInfo(stream_index=1, language=language, title=title)) is expected


def test_french_first_keeps_the_order_of_the_other_tracks():
    tracks = [AudioTrackInfo(i, language) for i, language in enumerate(["eng", "ger", "fre", "ita", "fra"], 1)]
    assert [t.language for t in french_first(tracks)] == ["fre", "fra", "eng", "ger", "ita"]


def media_with_subtitles(codecs):
    return MediaFileInfo(
        file_path="in.mkv",
        video_tracks=[VideoTrackInfo(stream_index=0)],
        audio_tracks=[AudioTrackInfo(1, "eng", is_default=True), AudioTrackInfo(2, "fre")],
        subtitle_tracks=[SubtitleTrackInfo(3 + i, codec=codec) for i, codec in enumerate(codecs)],
    )


def maps_of(cmd):
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]


def test_mp4_output_converts_text_subtitles_and_skips_image_ones():
    mapping = build_audio_mapping_options(media_with_subtitles(["subrip", "ass", "hdmv_pgs_subtitle"]),
                                          AudioProcessingOptions(keep_all_audio=True))
    cmd = build_ffmpeg_command("in.mkv", "out.mp4", mapping)
    assert maps_of(cmd) == ["0:v", "0:a:0", "0:a:1", "0:s:0", "0:s:1"]
    assert cmd[cmd.index("-c:s") + 1] == "mov_text"


def test_mkv_output_copies_every_subtitle():
    mapping = build_audio_mapping_options(media_with_subtitles(["subrip", "hdmv_pgs_subtitle"]),
                                          AudioProcessingOptions(keep_all_audio=True))
    cmd = build_ffmpeg_command("in.mkv", "out.mkv", mapping)
    assert maps_of(cmd)[-2:] == ["0:s:0", "0:s:1"]
    assert cmd[cmd.index("-c:s") + 1] == "copy"


def test_selected_default_track_gets_the_default_disposition():
    options = AudioProcessingOptions(selected_tracks=[1, 2], default_track_index=2)
    cmd = build_ffmpeg_command("in.mkv", "out.mkv", build_audio_mapping_options(media_with_subtitles([]), options))
    assert cmd[cmd.index("-disposition:a:0") + 1] == "0"
    assert cmd[cmd.index("-disposition:a:1") + 1] == "default"
