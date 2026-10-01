import pytest

import encoders
from encoders import BY_NAME, ENCODERS


def option(args, name):
    return args[args.index(name) + 1]


@pytest.mark.parametrize("encoder", ENCODERS, ids=lambda e: e.name)
def test_bitrate_args_select_the_encoder_and_the_bitrate(encoder):
    args = encoders.bitrate_args(encoder, 2500)
    assert option(args, "-c:v") == encoder.name
    assert option(args, "-b:v") == "2500k"
    if encoder.codec == "HEVC":
        assert option(args, "-tag:v") == "hvc1"  # required by Apple players for HEVC in MP4


@pytest.mark.parametrize("encoder", ENCODERS, ids=lambda e: e.name)
def test_every_encoder_gets_8_bit_420_frames(encoder):
    vf = option(encoders.filter_args(encoder, ["subtitles=subtitles.srt"]), "-vf")
    assert vf.startswith("subtitles=subtitles.srt,")  # the burned subtitles stay first
    assert vf.endswith("format=nv12,hwupload" if encoder.hardware == "VAAPI" else "format=yuv420p")


def test_vaapi_needs_its_device():
    assert encoders.input_args(BY_NAME["hevc_vaapi"]) == ["-vaapi_device", encoders.VAAPI_DEVICE]
    assert encoders.input_args(BY_NAME["hevc_nvenc"]) == []


def test_quality_args_use_crf_on_cpu_and_a_resolution_based_bitrate_on_gpu():
    assert option(encoders.quality_args(BY_NAME["libx264"], 1920, 1080, 24), "-crf") == "18"
    assert option(encoders.quality_args(BY_NAME["libsvtav1"], 1920, 1080, 24), "-crf") == "26"
    gpu = encoders.quality_args(BY_NAME["hevc_nvenc"], 1920, 1080, 24)
    assert option(gpu, "-b:v") == f"{int(1920 * 1080 * 24 * 0.08 / 1000)}k"
    assert "-crf" not in gpu


def test_single_pass_encoders_keep_a_larger_margin():
    assert encoders.size_margin(BY_NAME["libx264"]) < encoders.size_margin(BY_NAME["h264_nvenc"])
    assert [e.name for e in ENCODERS if e.two_pass] == ["libx264", "libx265"]


def test_available_encoders_lists_working_ones_gpu_first(monkeypatch):
    built = {"libx264", "libx265", "h264_nvenc", "hevc_nvenc", "av1_nvenc", "h264_vaapi"}
    working = {"libx264", "libx265", "h264_nvenc", "hevc_nvenc", "h264_vaapi"}  # av1_nvenc: GPU older than RTX 40
    monkeypatch.setattr(encoders, "_built_encoders", lambda: built)
    monkeypatch.setattr(encoders, "works", lambda encoder: encoder.name in working)
    monkeypatch.setattr(encoders.sys, "platform", "win32")
    encoders.available_encoders.cache_clear()
    try:
        names = [e.name for e in encoders.available_encoders()]
    finally:
        encoders.available_encoders.cache_clear()
    assert names == ["h264_nvenc", "hevc_nvenc", "libx264", "libx265"]  # no VAAPI outside Linux


def test_labels_name_the_codec_and_where_it_runs():
    assert BY_NAME["hevc_nvenc"].label == "HEVC - NVIDIA GPU (hevc_nvenc)"
    assert BY_NAME["libsvtav1"].label == "AV1 - CPU (libsvtav1)"
