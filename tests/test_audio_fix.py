from audio_fix import build_audio_fix_command
from audio_tracks import AudioTrackInfo, MediaFileInfo


def movie():
    return MediaFileInfo(file_path="in.mkv", audio_tracks=[
        AudioTrackInfo(1, "eng", title="VO", is_default=True, disposition_flags=["comment"]),
        AudioTrackInfo(2, "ger"),
        AudioTrackInfo(3, "fre", title="VFF", disposition_flags=["dub"]),
        AudioTrackInfo(4, None, title="VFQ 2.0"),
        AudioTrackInfo(5, "fre", title="Audiodescription", disposition_flags=["visual_impaired"]),
    ])


def maps_of(cmd):
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]


def dispositions_of(cmd):
    return {arg: cmd[i + 1] for i, arg in enumerate(cmd) if arg.startswith("-disposition")}


def test_every_audio_track_is_kept_with_the_french_ones_first():
    cmd, tracks, has_french = build_audio_fix_command("in.mkv", "out.mkv", movie())
    assert has_french
    assert [t.stream_index for t in tracks] == [3, 4, 5, 1, 2]
    assert maps_of(cmd) == ["0:v?", "0:3", "0:4", "0:5", "0:1", "0:2", "0:s?", "0:t?"]


def test_first_french_track_becomes_default_and_other_flags_are_kept():
    cmd, _, _ = build_audio_fix_command("in.mkv", "out.mkv", movie())
    # Only the tracks whose default flag changes get a -disposition (it replaces every flag)
    assert dispositions_of(cmd) == {"-disposition:a:0": "default+dub", "-disposition:a:3": "comment"}


def test_audio_is_downmixed_and_the_rest_copied():
    cmd, _, _ = build_audio_fix_command("in.mkv", "out.mkv", movie(), 2, 48000, "160k")
    assert cmd[cmd.index("-c") + 1] == "copy"
    for option, value in (("-c:a", "aac"), ("-ac", "2"), ("-ar", "48000"), ("-b:a", "160k")):
        assert cmd[cmd.index(option) + 1] == value


def test_mp4_output_has_no_attachment_mapping():
    cmd, _, _ = build_audio_fix_command("in.mp4", "out.mp4", movie())
    assert "0:t?" not in maps_of(cmd)


def test_without_french_track_the_order_and_flags_are_unchanged():
    media = MediaFileInfo(file_path="in.mkv", audio_tracks=[
        AudioTrackInfo(1, "eng", is_default=True), AudioTrackInfo(2, "ger")])
    cmd, tracks, has_french = build_audio_fix_command("in.mkv", "out.mkv", media)
    assert not has_french
    assert [t.stream_index for t in tracks] == [1, 2]
    assert dispositions_of(cmd) == {}
