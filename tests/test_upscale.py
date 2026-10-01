import io
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


def test_temp_space_is_bounded_by_a_few_chunks():
    # A two-hour 480p movie: whatever its length, only a few chunks of frames are on the disk at once
    movie = {"width": 720, "height": 480, "duration": 7200.0, "fps": "24/1"}
    frames = gu.chunk_frames(720, 480, 4)
    expected = frames * 720 * 480 * (2 * gu.PNG_BYTES_PER_PIXEL + 3 * 16 * gu.JPEG_BYTES_PER_PIXEL)
    assert gu.estimate_temp_space(movie, 4) == int(expected)
    assert gu.estimate_temp_space(movie, 4) < 5e9


def test_short_videos_need_less_than_a_chunk():
    clip = {"width": 320, "height": 180, "duration": 2.0, "fps": "1/1"}
    per_frame = 320 * 180 * (2 * gu.PNG_BYTES_PER_PIXEL + 3 * 16 * gu.JPEG_BYTES_PER_PIXEL)
    assert gu.estimate_temp_space(clip, 4) == int(2 * per_frame)


@pytest.mark.parametrize("width, height, scale, expected", [
    (720, 480, 4, int(gu.CHUNK_BYTES / (720 * 480 * 16 * gu.JPEG_BYTES_PER_PIXEL))),
    (7680, 4320, 4, 8),     # at least 8 frames (one 8K frame x4 weighs about 265 MB)
    (160, 90, 2, 1000),     # at most 1000 frames
])
def test_chunk_frames(width, height, scale, expected):
    assert gu.chunk_frames(width, height, scale) == expected


@pytest.mark.parametrize("model_name, source, target, scale", [
    ("realesrgan-x4plus", 480, 720, 4),       # x4 network: always x4, ffmpeg resizes to 720 lines
    ("realesr-animevideov3", 480, 720, 2),    # 1.5 -> the x2 network
    ("realesr-animevideov3", 360, 1080, 3),   # 3 -> x3
    ("realesr-animevideov3", 480, 2160, 4),   # 4.5 -> the largest, x4, ffmpeg resizes the rest
])
def test_model_scale_uses_the_smallest_native_scale_that_is_enough(model_name, source, target, scale):
    model = next(m for m in gu.MODELS if m.name == model_name)
    assert gu.model_scale(model, source, target) == scale


def png(fill):
    """A minimal PNG-like image: signature, one data chunk, IEND (enough for the splitter)."""
    data = bytes([fill]) * 5
    return (gu.PNG_SIGNATURE + len(data).to_bytes(4, "big") + b"IDAT" + data + b"CRC!"
            + (0).to_bytes(4, "big") + b"IEND" + b"CRC!")


def test_read_png_frames_splits_concatenated_images():
    images = [png(1), png(2), png(3)]
    assert list(gu.read_png_frames(io.BytesIO(b"".join(images)))) == images


def test_read_png_frames_reports_a_truncated_stream():
    with pytest.raises(gu.UpscaleError):
        list(gu.read_png_frames(io.BytesIO(png(1) + png(2)[:-6])))


@pytest.mark.parametrize("height, expected", [
    (480, [720, 1080, 2160]),
    (720, [1080, 2160]),
    (1080, [2160]),
    (2160, []),
])
def test_only_higher_resolutions_are_offered(height, expected):
    assert [h for _, h in gu.upscale_resolution_choices(640, height)] == expected


@pytest.mark.parametrize("size, expected", [(0, "1 MB"), (54e6, "54 MB"), (999e6, "999 MB"), (3.5e9, "3.5 GB")])
def test_format_size(size, expected):
    assert gu._format_size(size) == expected


@pytest.mark.parametrize("answer", [True, False])
def test_the_temporary_space_is_always_announced_and_can_be_refused(monkeypatch, answer):
    questions = []
    monkeypatch.setattr(gu.messagebox, "askyesno", lambda title, message, **options: questions.append(
        (title, message, options)) or answer)
    assert gu.confirm_temp_space(None, 3.5e9, 120e9, "D:/Films") is answer
    [(title, message, options)] = questions
    assert title == "Temporary disk space" and options["icon"] == "question" and options["default"] == "yes"
    assert "about 3.5 GB" in message and "D:/Films" in message and "Free space: 120.0 GB" in message


def test_not_enough_space_is_a_warning_answered_no_by_default(monkeypatch):
    questions = []
    monkeypatch.setattr(gu.messagebox, "askyesno", lambda title, message, **options: questions.append(
        (title, message, options)) or False)
    assert not gu.confirm_temp_space(None, 3.5e9, 2e9, "D:/Films")
    [(title, message, options)] = questions
    assert title == "Not enough disk space" and options["icon"] == "warning" and options["default"] == "no"
    assert "not enough" in message


@pytest.mark.parametrize("seconds, expected", [(0, "00:00"), (59, "00:59"), (3599, "59:59"), (3725, "1:02:05"),
                                               (47 * 3600, "47:00:00"), (235 * 3600 + 59, "9 days 19 h")])
def test_format_duration(seconds, expected):
    assert gu._format_duration(seconds) == expected


@pytest.mark.parametrize("seconds_per_frame, expected", [(0.25, "4.0 frames/s"), (7.4, "7 s per frame"),
                                                         (600, "10:00 per frame")])
def test_speed_text(seconds_per_frame, expected):
    assert gu._speed_text(seconds_per_frame) == expected


HEADER = "[0 Intel(R) UHD Graphics]  queueC=1[1]  queueG=0[1]  queueT=2[1]\n"


def tiles(count):
    return "".join(f"{100 * i / count:.2f}%\n" for i in range(count))


@pytest.mark.parametrize("log, finished, frames", [
    (HEADER, 0, 0),
    (HEADER + "0.00%\n", 0, 0),  # first tile in progress: the number of tiles is not known yet
    (HEADER + "0.00%\n25.00%\n50.00%\n", 0, 0.5),  # third tile in progress: 2 of 4 finished
    (HEADER + "0.00%\n0.00%\n25.00%\n25.00%\n50.00%\n", 0, 0.75),  # two frames at a time: 2 + 1 tiles
    (HEADER + tiles(60) * 2 + "0.00%\n", 2, 2),  # 60 tiles a frame, 2 frames saved, the third one starts
    (HEADER + tiles(60) * 2 + "0.00%\n", 1, 1 + 59 / 60),  # the second frame is not saved yet
    (HEADER + tiles(4) * 2, 2, 2),  # real log of 2 frames
])
def test_frames_done_counts_the_finished_tiles_of_the_frames_in_progress(log, finished, frames):
    # Upscaling a 1080p frame x4 on an integrated GPU takes minutes: the time left must not wait for it
    assert gu.frames_done(log, finished) == pytest.approx(frames)


def test_log_tail_skips_realesrgan_progress_lines(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("[0 GPU]  fp16=1\n0.00%\n25.00%\nvkCreateInstance failed\n100.00%\n", encoding="utf-8")
    assert gu._log_tail(str(log)) == "[0 GPU]  fp16=1\nvkCreateInstance failed"


def test_executable_name_matches_the_platform():
    assert os.path.basename(gu.REALESRGAN_EXE).endswith(".exe") == (sys.platform == "win32")
