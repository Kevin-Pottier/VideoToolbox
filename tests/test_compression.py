import pytest

from audio_tracks import AudioTrackInfo, MediaFileInfo, SubtitleTrackInfo, VideoTrackInfo
from compression import (AUDIO_BITRATE, MIN_VIDEO_BITRATE_KBPS, SIZE_MARGIN, CompressionSettings,
                         compute_video_bitrate_kbps)

# A film with the English audio first and the French one second, text and bitmap (PGS) subtitles
FILM = MediaFileInfo("in.mkv", video_tracks=[VideoTrackInfo(0, "h264", 1920, 1080)],
                     audio_tracks=[AudioTrackInfo(1, "eng", channels=2, is_default=True), AudioTrackInfo(2, "fre", channels=6)],
                     subtitle_tracks=[SubtitleTrackInfo(3, "eng", codec="subrip"),
                                      SubtitleTrackInfo(4, "fre", codec="hdmv_pgs_subtitle")])

GIB_IN_BITS = 1024 ** 3 * 8


def test_budget_fills_the_target_size_minus_the_margin():
    duration = 3600
    kbps = compute_video_bitrate_kbps(1.0, duration, AUDIO_BITRATE)
    total_bits = (kbps * 1000 + AUDIO_BITRATE) * duration
    budget = GIB_IN_BITS * (1 - SIZE_MARGIN)
    assert total_bits <= budget
    assert budget - total_bits < 1000 * duration  # only the rounding to the kbps is lost


def test_each_encoded_audio_track_costs_the_encoded_audio_bitrate():
    one_track = compute_video_bitrate_kbps(2.0, 5400, AUDIO_BITRATE)
    two_tracks = compute_video_bitrate_kbps(2.0, 5400, 2 * AUDIO_BITRATE)
    assert abs((one_track - two_tracks) - AUDIO_BITRATE / 1000) <= 1


def test_video_without_audio_gets_the_whole_budget():
    assert compute_video_bitrate_kbps(1.0, 100, 0) > compute_video_bitrate_kbps(1.0, 100, AUDIO_BITRATE)


def test_too_small_target_is_below_the_minimum():
    # 0.1 MiB for 20 s leaves a negative budget once the 192 kbps audio is counted
    assert compute_video_bitrate_kbps(0.0001, 20, AUDIO_BITRATE) < MIN_VIDEO_BITRATE_KBPS


def two_pass(sub_option="none", sub_path=None, ext="mp4", encoder="libx264", settings=CompressionSettings()):
    from compression import build_encode_commands
    from encoders import BY_NAME
    return build_encode_commands("in.mkv", "out." + ext, ext, 1500, sub_option, sub_path, "work", FILM, "-fps_mode",
                                 BY_NAME[encoder], settings)


def option(cmd, name):
    return cmd[cmd.index(name) + 1]


def maps(cmd):
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]


def test_every_audio_track_is_kept_french_first_whatever_the_subtitle_option():
    # Before, only "soft" kept every track: otherwise ffmpeg kept one, here the English one
    for sub_option, sub_path in (("none", None), ("hard", "work/subtitles.srt")):
        (pass1, _), (pass2, _) = two_pass(sub_option, sub_path, ext="mkv")
        assert maps(pass1) == ["0:v:0"]
        assert maps(pass2) == ["0:v:0", "0:2", "0:1", "0:3", "0:4", "0:t?"]
        assert option(pass2, "-disposition:a:0") == "default" and option(pass2, "-disposition:a:1") == "0"


def test_other_audio_flags_are_kept_and_nothing_changes_without_french_track():
    from compression import output_streams
    film = MediaFileInfo("in.mkv", audio_tracks=[
        AudioTrackInfo(1, "eng", is_default=True), AudioTrackInfo(2, "fre", disposition_flags=["visual_impaired", "dub"])])
    args = output_streams(film, "mkv", False)
    assert option(args, "-disposition:a:0") == "default+visual_impaired+dub"
    assert option(args, "-disposition:a:1") == "0"
    english_only = MediaFileInfo("in.mkv", audio_tracks=[AudioTrackInfo(1, "eng"), AudioTrackInfo(2, "ger", is_default=True)])
    args = output_streams(english_only, "mkv", False)
    assert maps(args)[1:3] == ["0:1", "0:2"] and "-disposition:a:0" not in args


def test_mp4_keeps_the_text_subtitles_of_the_source():
    pass2 = two_pass(ext="mp4")[1][0]
    assert maps(pass2) == ["0:v:0", "0:2", "0:1", "0:3"]  # PGS cannot go in MP4
    assert option(pass2, "-c:s") == "mov_text" and "-disposition:s:0" not in pass2


def test_added_soft_subtitles_come_first_and_are_the_default():
    pass2 = two_pass("soft", "work/subtitles.srt", "mkv")[1][0]
    assert pass2[pass2.index("-i") + 3] == "work/subtitles.srt"
    assert maps(pass2) == ["0:v:0", "0:2", "0:1", "1:0", "0:3", "0:4", "0:t?"]
    assert [option(pass2, f"-disposition:s:{i}") for i in range(3)] == ["default", "0", "0"]


def test_mov_text_subtitles_become_srt_in_mkv():
    from compression import build_copy_command
    mp4_source = MediaFileInfo("in.mp4", subtitle_tracks=[SubtitleTrackInfo(2, codec="mov_text")])
    cmd = build_copy_command("in.mp4", "out.mkv", "mkv", "none", None, mp4_source)
    assert option(cmd, "-c:s") == "copy" and option(cmd, "-c:s:0") == "srt"


def test_first_pass_only_analyses_the_video():
    (pass1, share1), (pass2, share2) = two_pass()
    assert option(pass1, "-pass") == "1" and "-an" in pass1 and pass1[-3:] == ["-f", "null", "-"]
    assert option(pass2, "-pass") == "2" and option(pass2, "-b:a:0") == "192k" and pass2[-1] == "out.mp4"
    assert 0 < share1 < share2 and share1 + share2 == 1


def test_both_passes_encode_the_same_frames_with_the_same_settings():
    # Without passthrough timestamps the MP4 output of pass 2 duplicates a frame that pass 1 did not
    # analyse: x264 then fails ("Incomplete MB-tree stats file") or hangs
    passes = [cmd for cmd, _ in two_pass()]
    for name in ("-fps_mode", "-c:v", "-b:v", "-preset", "-passlogfile"):
        assert option(passes[0], name) == option(passes[1], name)
    assert option(passes[0], "-fps_mode") == "passthrough"


def test_burned_subtitles_are_rendered_in_both_passes():
    for cmd, _ in two_pass("hard", "work/subtitles.srt"):
        assert option(cmd, "-vf").startswith("subtitles=subtitles.srt,")  # relative to the working directory


def test_soft_subtitles_codec_depends_on_the_container():
    assert option(two_pass("soft", "work/subtitles.srt", "mp4")[1][0], "-c:s") == "mov_text"
    assert option(two_pass("soft", "work/subtitles.srt", "mkv")[1][0], "-c:s") == "copy"


def test_a_stuck_ffmpeg_is_killed(monkeypatch):
    import sys
    import time

    import compression
    monkeypatch.setattr(compression, "STALL_TIMEOUT", 1)
    silent_command = [sys.executable, "-c", "import time; time.sleep(60)"]
    start = time.time()
    with pytest.raises(compression.CompressionError, match="stopped responding"):
        compression._encode([(silent_command, 1.0)], 10, None, lambda *progress: None)
    assert time.time() - start < 15


def test_default_settings_keep_the_former_commands():
    pass2 = two_pass()[1][0]
    assert option(pass2, "-preset") == "medium" and option(pass2, "-vf") == "format=yuv420p"
    assert option(pass2, "-c:a") == "aac" and option(pass2, "-ac") == "2" and "-af" not in pass2
    assert (option(pass2, "-b:a:0"), option(pass2, "-b:a:1")) == ("192k", "192k")


def test_the_speed_sets_the_preset_of_both_passes():
    for cmd, _ in two_pass(settings=CompressionSettings(speed="fast")):
        assert option(cmd, "-preset") == "veryfast"


def test_a_taller_video_is_reduced_in_both_passes_then_the_subtitles_are_burned():
    settings = CompressionSettings(max_height=720)
    for cmd, _ in two_pass("hard", "work/subtitles.srt", settings=settings):
        # Drawn after the resize: the subtitles stay sharp at the output resolution
        assert option(cmd, "-vf") == "scale=-2:720:flags=lanczos,subtitles=subtitles.srt,format=yuv420p"
    # A video not taller than the maximum keeps its resolution
    assert option(two_pass(settings=CompressionSettings(max_height=1080))[1][0], "-vf") == "format=yuv420p"


def test_audio_bitrate_and_surround():
    from compression import audio_bitrates
    stereo = two_pass(settings=CompressionSettings(audio_kbps=128))[1][0]
    assert option(stereo, "-b:a:0") == "128k" and option(stereo, "-ac") == "2"
    surround = two_pass(settings=CompressionSettings(audio_kbps=128, keep_surround=True))[1][0]
    assert "-ac" not in surround and option(surround, "-af") == "aformat=channel_layouts=mono|stereo|5.1|7.1"
    # Output order: the French 5.1 first, at twice the bitrate, then the English stereo
    assert (option(surround, "-b:a:0"), option(surround, "-b:a:1")) == ("256k", "128k")
    assert audio_bitrates(FILM, CompressionSettings(audio_kbps=128, keep_surround=True)) == [256000, 128000]
    assert audio_bitrates(FILM) == [192000, 192000]


@pytest.mark.parametrize("codec, encoder", [("opus", "libopus"), ("ac3", "ac3"), ("eac3", "eac3")])
def test_other_audio_codecs(codec, encoder):
    pass2 = two_pass(settings=CompressionSettings(audio_codec=codec, audio_kbps=128))[1][0]
    assert option(pass2, "-c:a") == encoder and option(pass2, "-b:a:0") == "128k"


def test_the_original_audio_is_copied_and_counted_at_its_bitrate():
    from compression import audio_bitrates
    settings = CompressionSettings(audio_codec="copy", audio_kbps=96, keep_surround=True)
    pass2 = two_pass(settings=settings)[1][0]
    assert option(pass2, "-c:a") == "copy"
    assert not [arg for arg in pass2 if arg.startswith("-b:a") or arg in ("-ac", "-af", "-ar")]
    film = MediaFileInfo("in.mkv", audio_tracks=[AudioTrackInfo(1, "eng", bit_rate=640000),
                                                 AudioTrackInfo(2, "fre", bit_rate=448000)])
    assert audio_bitrates(film, settings) == [448000, 640000]  # French first


def test_x265_two_passes_share_a_relative_statistics_file():
    (pass1, _), (pass2, _) = two_pass(encoder="libx265")
    assert option(pass1, "-x265-params") == "pass=1:stats=x265_2pass.log:log-level=error"
    assert option(pass2, "-x265-params") == "pass=2:stats=x265_2pass.log:log-level=error"


def test_gpu_encoders_use_a_single_pass():
    [(cmd, share)] = two_pass(encoder="hevc_nvenc")
    assert share == 1 and "-pass" not in cmd and option(cmd, "-c:v") == "hevc_nvenc"
    assert option(cmd, "-fps_mode") == "passthrough" and cmd[-1] == "out.mp4"


def test_vaapi_device_comes_before_the_input():
    [(cmd, _)] = two_pass(encoder="h264_vaapi")
    assert cmd.index("-vaapi_device") < cmd.index("-i")


def test_copy_command_keeps_the_streams_as_they_are():
    from compression import build_copy_command
    mp4 = build_copy_command("in.mkv", "out.mp4", "mp4", "soft", "work/subtitles.srt", FILM)
    assert option(mp4, "-c") == "copy" and option(mp4, "-c:s") == "mov_text"
    assert maps(mp4) == ["0:v:0", "0:2", "0:1", "1:0", "0:3"]
    mkv = build_copy_command("in.mkv", "out.mkv", "mkv", "none", None, FILM)
    assert option(mkv, "-c:s") == "copy" and maps(mkv) == ["0:v:0", "0:2", "0:1", "0:3", "0:4", "0:t?"]
