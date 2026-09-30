from compression import AUDIO_BITRATE, MIN_VIDEO_BITRATE_KBPS, SIZE_MARGIN, compute_video_bitrate_kbps

GIB_IN_BITS = 1024 ** 3 * 8


def test_budget_fills_the_target_size_minus_the_margin():
    duration = 3600
    kbps = compute_video_bitrate_kbps(1.0, duration, 1)
    total_bits = (kbps * 1000 + AUDIO_BITRATE) * duration
    budget = GIB_IN_BITS * (1 - SIZE_MARGIN)
    assert total_bits <= budget
    assert budget - total_bits < 1000 * duration  # only the rounding to the kbps is lost


def test_each_encoded_audio_track_costs_the_encoded_audio_bitrate():
    one_track = compute_video_bitrate_kbps(2.0, 5400, 1)
    two_tracks = compute_video_bitrate_kbps(2.0, 5400, 2)
    assert abs((one_track - two_tracks) - AUDIO_BITRATE / 1000) <= 1


def test_video_without_audio_gets_the_whole_budget():
    assert compute_video_bitrate_kbps(1.0, 100, 0) > compute_video_bitrate_kbps(1.0, 100, 1)


def test_too_small_target_is_below_the_minimum():
    # 0.1 MiB for 20 s leaves a negative budget once the 192 kbps audio is counted
    assert compute_video_bitrate_kbps(0.0001, 20, 1) < MIN_VIDEO_BITRATE_KBPS


def two_pass(sub_option="none", sub_path=None, ext="mp4"):
    from compression import build_two_pass_commands
    return build_two_pass_commands("in.mkv", "out." + ext, ext, 1500, sub_option, sub_path, "work", "-fps_mode")


def option(cmd, name):
    return cmd[cmd.index(name) + 1]


def test_first_pass_only_analyses_the_video():
    (pass1, share1), (pass2, share2) = two_pass()
    assert option(pass1, "-pass") == "1" and "-an" in pass1 and pass1[-3:] == ["-f", "null", "-"]
    assert option(pass2, "-pass") == "2" and option(pass2, "-b:a") == "192k" and pass2[-1] == "out.mp4"
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
        assert option(cmd, "-vf") == "subtitles=subtitles.srt"  # relative to the working directory


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
    assert not compression._encode([(silent_command, 1.0)], 10, None, lambda *progress: None)
    assert time.time() - start < 15
