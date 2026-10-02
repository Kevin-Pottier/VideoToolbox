"""The shared ffmpeg runner: progress, errors, cancellation, time left. A Python script plays ffmpeg."""
import sys
import threading
import time

import pytest

import ffmpeg_progress
from ffmpeg_progress import Cancelled, Eta, FFmpegError, format_seconds, parse_time, run_ffmpeg


def fake_ffmpeg(*lines, delay=0.0, code=0, then_sleep=0):
    """Command printing the lines on stderr like ffmpeg (progress lines end with \\r), then exiting with code."""
    script = (f"import sys, time\nfor line in {list(lines)!r}:\n    sys.stderr.write(line)\n    sys.stderr.flush()\n"
              f"    time.sleep({delay})\ntime.sleep({then_sleep})\nsys.exit({code})")
    return [sys.executable, "-c", script]


@pytest.mark.parametrize("line, seconds", [
    ("frame=  240 fps=48 q=28.0 size=1024KiB time=00:00:10.00 bitrate=838.9kbits/s speed=2x\r", 10.0),
    ("size=  2048KiB time=01:02:03.5 bitrate=4.5kbits/s\r", 3723.5),
    ("size=       0KiB time=-00:00:00.04 bitrate=N/A\r", None),  # before the start
    ("size=       0KiB time=N/A bitrate=N/A\r", None),
    ("Stream #0:0: Video: h264\n", None),
])
def test_progress_lines(line, seconds):
    assert parse_time(line) == seconds


def test_the_progress_is_the_share_of_the_duration():
    shares = []
    run_ffmpeg(fake_ffmpeg("Input #0\n", "time=00:00:02.50 bitrate=1\r", "time=00:00:05.00 bitrate=1\r",
                           "time=00:00:12.00 bitrate=1\r"), duration=10, report=shares.append)
    assert shares == [0.25, 0.5, 1.0]  # never more than the whole


def test_no_progress_without_a_duration():
    shares = []
    run_ffmpeg(fake_ffmpeg("time=00:00:02.50 bitrate=1\r"), duration=None, report=shares.append)
    assert shares == []


def test_a_failure_gives_the_last_lines_of_ffmpeg():
    lines = [f"line {i}\n" for i in range(20)] + ["Error opening input: Invalid data found\n"]
    with pytest.raises(FFmpegError) as error:
        run_ffmpeg(fake_ffmpeg(*lines, code=1), duration=10)
    message = str(error.value).splitlines()
    assert message[-1] == "Error opening input: Invalid data found" and len(message) == 8


def test_a_silent_failure_gives_the_exit_code():
    with pytest.raises(FFmpegError, match="exited with code 3"):
        run_ffmpeg(fake_ffmpeg(code=3))


def test_cancel_kills_ffmpeg():
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    start = time.time()
    with pytest.raises(Cancelled):
        run_ffmpeg(fake_ffmpeg("time=00:00:01.00 bitrate=1\r", then_sleep=60), duration=10, cancel=cancel)
    assert time.time() - start < 5


def test_a_stuck_ffmpeg_is_killed(monkeypatch):
    monkeypatch.setattr(ffmpeg_progress, "STALL_TIMEOUT", 1)
    with pytest.raises(FFmpegError, match="stopped responding for 1 s"):
        run_ffmpeg(fake_ffmpeg("time=00:00:01.00 bitrate=1\r", then_sleep=60), duration=10)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_the_time_left_is_measured_from_the_first_progress():
    clock = Clock()
    eta = Eta(clock)
    clock.now += 30  # the start of ffmpeg (analysis...) does not count
    assert eta.update(0.1) is None
    clock.now += 10
    assert eta.update(0.2) == pytest.approx(80)  # 10 s per 10 %, 80 % left
    clock.now += 20
    assert eta.update(0.3) == pytest.approx(105)  # slower: 15 s per 10 %
    assert eta.update(0.3) == pytest.approx(105)


def test_a_job_starting_again_is_measured_again():
    # A copy that failed, encoded instead: the share goes back to 0
    clock = Clock()
    eta = Eta(clock)
    eta.update(0.5)
    clock.now += 1
    assert eta.update(0.9) is not None
    clock.now += 1
    assert eta.update(0.05) is None
    clock.now += 100
    assert eta.update(0.1) == pytest.approx(1800)


@pytest.mark.parametrize("seconds, text", [(None, "--:--"), (0, "00:00"), (342.7, "05:42"), (3942, "1:05:42")])
def test_format_seconds(seconds, text):
    assert format_seconds(seconds) == text


def test_console_progress(capsys):
    report = ffmpeg_progress.console_progress("Compressing")
    report(0.5)
    report(1.0)
    out = capsys.readouterr().out
    assert "Compressing: [====================--------------------] 50%" in out and out.endswith("100% | ETA: 00:00\n")
