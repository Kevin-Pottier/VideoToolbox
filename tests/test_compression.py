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
