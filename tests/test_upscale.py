import math
import os
import sys

import pytest

import gui_upscale as gu


@pytest.mark.parametrize("rate, expected", [
    ("24000/1001", 24000 / 1001),
    ("25/1", 25.0),
    ("30", 30.0),
    ("0/0", 0.0),
    (None, 0.0),
    ("abc", 0.0),
])
def test_rate_to_float(rate, expected):
    assert gu._rate_to_float(rate) == pytest.approx(expected)


def test_estimate_frame_count_rounds_up():
    assert gu.estimate_frame_count({"duration": 10.0, "fps": "24000/1001"}) == math.ceil(10 * 24000 / 1001)


def test_estimate_temp_space_counts_source_and_upscaled_frames():
    info = {"width": 320, "height": 180, "duration": 2.0, "fps": "1/1"}
    per_frame = 320 * 180 * (1 + gu.MODEL_SCALE ** 2) * gu.JPEG_BYTES_PER_PIXEL
    assert gu.estimate_temp_space(info) == int(2 * per_frame)


@pytest.mark.parametrize("height, expected", [
    (480, [720, 1080, 2160]),
    (720, [1080, 2160]),
    (1080, [2160]),
    (2160, []),
])
def test_only_higher_resolutions_are_offered(height, expected):
    assert [h for _, h in gu.upscale_resolution_choices(640, height)] == expected


@pytest.mark.parametrize("seconds, expected", [(0, "00:00"), (59, "00:59"), (3599, "59:59"), (3725, "1:02:05")])
def test_format_duration(seconds, expected):
    assert gu._format_duration(seconds) == expected


def test_log_tail_skips_realesrgan_progress_lines(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("[0 GPU]  fp16=1\n0.00%\n25.00%\nvkCreateInstance failed\n100.00%\n", encoding="utf-8")
    assert gu._log_tail(str(log)) == "[0 GPU]  fp16=1\nvkCreateInstance failed"


def test_executable_name_matches_the_platform():
    assert os.path.basename(gu.REALESRGAN_EXE).endswith(".exe") == (sys.platform == "win32")
