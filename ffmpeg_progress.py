"""
Running ffmpeg with its progress, for every feature: the progress lines ("time=00:01:02.50") give the share of
the video done, a stuck ffmpeg is killed, and the job can be stopped by the user (cancel event).

The time left is computed by Eta from the shares reported: the speed is measured from the first progress, so
that the start of ffmpeg (opening the file, first pass analysis) does not count.
"""
import collections
import re
import subprocess
import sys
import threading
import time

STALL_TIMEOUT = 300  # seconds without any ffmpeg output after which ffmpeg is considered stuck and killed
PROGRESS_TIME = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


class FFmpegError(RuntimeError):
    """ffmpeg failed: the message holds its last lines (the reason)."""


class Cancelled(Exception):
    """The user stopped the job."""


def parse_time(line):
    """Seconds of video done according to an ffmpeg progress line, or None."""
    match = PROGRESS_TIME.search(line)
    if not match:
        return None
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def run_ffmpeg(cmd, duration=None, report=None, cwd=None, cancel=None):
    """
    Run an ffmpeg command; report(share of the duration done, 0 to 1) is called on each progress line when the
    duration (seconds) is known.
    Raises:
        FFmpegError: ffmpeg failed (its last lines), or wrote nothing for STALL_TIMEOUT s (killed).
        Cancelled: cancel (threading.Event) was set; ffmpeg was killed.
    """
    # ffmpeg writes UTF-8 (file names): the locale encoding (cp1252 on Windows) could fail on it
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    last_lines = collections.deque(maxlen=8)  # the reason, if ffmpeg fails
    last_output = [time.time()]
    killed = []  # why the watchdog killed ffmpeg: "stalled" or "cancelled"

    def watchdog():
        # A stuck ffmpeg ignores the usual termination request: kill it
        while proc.poll() is None:
            if cancel is not None and cancel.is_set():
                killed.append("cancelled")
            elif time.time() - last_output[0] > STALL_TIMEOUT:
                killed.append("stalled")
            if killed:
                proc.kill()
                return
            time.sleep(0.2)
    threading.Thread(target=watchdog, daemon=True).start()
    for line in proc.stderr:  # progress lines end with \r, split like \n
        last_output[0] = time.time()
        last_lines.append(line.rstrip())
        seconds = parse_time(line)
        if seconds is not None and duration and report:
            report(min(1.0, seconds / duration))
    proc.wait()
    if killed == ["cancelled"]:
        raise Cancelled()
    if killed:
        raise FFmpegError(f"ffmpeg stopped responding for {STALL_TIMEOUT} s and was killed")
    if proc.returncode != 0:
        raise FFmpegError("\n".join(last_lines) or f"ffmpeg exited with code {proc.returncode}")


class Eta:
    """Time left of a job from the shares done (0 to 1), measured from the first progress."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.first = None  # (time, share) of the first progress
        self.last = 0.0

    def update(self, share):
        """Seconds left, or None while the speed is unknown."""
        now = self.clock()
        if share < self.last:
            self.first = None  # the job started again (a copy that failed, encoded instead): measured again
        self.last = share
        if share >= 1:
            return 0.0
        if self.first is None:
            if share > 0:
                self.first = (now, share)
            return None
        start, start_share = self.first
        if share <= start_share or now <= start:
            return None
        return (now - start) / (share - start_share) * (1 - share)


def format_seconds(seconds):
    """'05:42', '1:05:42', or '--:--' when unknown."""
    if seconds is None:
        return "--:--"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def console_progress(label):
    """report(share) printing a progress bar with the time left in the terminal (no window)."""
    eta = Eta()

    def report(share):
        filled = int(round(40 * share))
        sys.stdout.write(f"\r{label}: [{'=' * filled}{'-' * (40 - filled)}] {int(share * 100)}% | "
                         f"ETA: {format_seconds(eta.update(share))}")
        if share >= 1:
            sys.stdout.write("\n")
        sys.stdout.flush()
    return report
