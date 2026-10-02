"""
The windows of the application, opened for real and clicked by a robot (Tk timers): run under a display, or in
a virtual one on Linux (xvfb-run python -m pytest). Skipped without a display.
"""
import gc
import threading
import time
import tkinter as tk

import pytest

import audio_codecs
import encoders
import gui_helpers
from compression import COPY_AUDIO
from ffmpeg_progress import Cancelled
from gui_helpers import CANCELLED, JobResult


def has_display():
    try:
        tk.Tk().destroy()
        return True
    except tk.TclError:
        return False
    finally:
        # A Tk interpreter freed by the garbage collector in a worker thread aborts Python ("Tcl_AsyncDelete:
        # async handler deleted by the wrong thread"): the destroyed ones are freed here, in the main thread
        gc.collect()


pytestmark = pytest.mark.skipif(not has_display(), reason="no display (on Linux: xvfb-run python -m pytest)")


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def text_of(widget):
    try:
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end")
        return str(widget.cget("text")) if "text" in widget.keys() else ""
    except tk.TclError:
        return ""


class Robot:
    """Clicks in the windows once they are open: its actions run one after the other, from the Tk event loop."""

    def __init__(self, root):
        self.root = root
        self.delay = 0
        self.errors = []
        self.seen = []
        self.timers = []

    def windows(self):
        return [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel) and w.winfo_exists()]

    def do(self, action, delay=120):
        self.delay += delay
        self.timers.append(self.root.after(self.delay, self._run, action))

    def stop(self):
        """Cancel the actions not run yet, close the windows left open."""
        for timer in self.timers:
            self.root.after_cancel(timer)
        for window in self.windows():
            window.destroy()

    def _run(self, action):
        try:
            action()
        except Exception as e:  # the test fails, and the windows are closed so that it does not wait forever
            self.errors.append(repr(e))
            for window in self.windows():
                window.destroy()

    def find(self, text):
        for window in reversed(self.windows()):
            for widget in walk(window):
                if text_of(widget).startswith(text):
                    return widget
        raise LookupError(f"no widget {text!r}")

    def click(self, text):
        self.do(lambda: self.find(text).invoke())

    def tree_click(self, row, column):
        """Click a cell of the tree view of the last window (audio tracks)."""
        def click():
            tree = next(w for w in walk(self.windows()[-1]) if isinstance(w, tk.ttk.Treeview))
            x, y, width, height = tree.bbox(row, column)
            tree.event_generate("<Button-1>", x=x + width // 2, y=y + height // 2)
        self.do(click)

    def close(self):
        """The close button of the last window opened."""
        def close():
            window = self.windows()[-1]
            handler = window.protocol("WM_DELETE_WINDOW")
            window.tk.call(handler) if handler else window.destroy()
        self.do(close)

    def read(self):
        """Keep the texts of the open windows (self.seen)."""
        self.do(lambda: self.seen.append("\n".join(text_of(w) for window in self.windows() for w in walk(window))))


@pytest.fixture(scope="module")
def root():
    """
    One root for the tests, as in the application: on Windows, creating Tk interpreters again and again in one
    process ends up failing ("Can't find a usable tk.tcl").
    """
    root = gui_helpers.app_root()
    yield root
    gui_helpers.close_app()
    del root
    gc.collect()  # see has_display


@pytest.fixture
def robot(root):
    robot = Robot(root)
    yield robot
    robot.stop()
    assert robot.errors == []


@pytest.fixture
def messages(monkeypatch):
    """The message boxes shown, as (kind, title, text), instead of waiting for a click."""
    shown = []
    monkeypatch.setattr(gui_helpers, "show_message", lambda kind, title, text: shown.append((kind, title, text)))
    return shown


# ---- run_jobs

def test_jobs_run_in_parallel_and_give_their_results(robot):
    started = threading.Barrier(2, timeout=5)  # both jobs running at the same time

    def work(index, report, cancel):
        started.wait()
        report(0.5)
        if index == 1:
            raise RuntimeError("ffmpeg failed:\nInvalid data")
        return f"out{index}.mkv"
    results = gui_helpers.run_jobs("Compression", ["a.mkv", "b.mkv"], work)
    assert results == [JobResult("a.mkv", True, "out0.mkv"), JobResult("b.mkv", False, "ffmpeg failed:\nInvalid data")]
    assert robot.windows() == []  # closed by itself


def test_the_window_shows_the_progress_and_the_time_left(robot):
    go = threading.Event()

    def work(index, report, cancel):
        report(0.25)
        time.sleep(0.3)
        report(0.5)
        go.wait(10)
        return "out.mkv"
    robot.do(lambda: None, delay=800)
    robot.read()
    robot.do(go.set)
    gui_helpers.run_jobs("Compression", ["film.mkv"], work, done_text=lambda path: f"made {path}")
    assert "film.mkv" in robot.seen[0] and "50% - time left: 00:00" in robot.seen[0]  # 0.3 s per 25 %


def test_closing_the_window_stops_the_jobs(robot, monkeypatch):
    questions = []
    monkeypatch.setattr(gui_helpers.messagebox, "askyesno", lambda *args, **kwargs: questions.append(args) or True)

    def work(index, report, cancel):
        while not cancel.wait(0.05):
            report(0.1)
        raise Cancelled()
    robot.do(lambda: None, delay=300)
    robot.close()
    results = gui_helpers.run_jobs("Compression", ["a.mkv", "b.mkv"], work)
    assert results == [JobResult("a.mkv", False, CANCELLED), JobResult("b.mkv", False, CANCELLED)]
    assert questions[0][0] == "Stop"


def test_closing_without_confirming_goes_on(robot, monkeypatch):
    monkeypatch.setattr(gui_helpers.messagebox, "askyesno", lambda *args, **kwargs: False)
    go = threading.Event()

    def work(index, report, cancel):
        go.wait(10)
        return "cancelled" if cancel.is_set() else "done"
    robot.close()
    robot.do(go.set)
    assert gui_helpers.run_jobs("Compression", ["a.mkv"], work) == [JobResult("a.mkv", True, "done")]


def test_many_jobs_are_in_a_scrolled_list(robot):
    results = gui_helpers.run_jobs("Batch", [f"video{i}.mkv" for i in range(8)], lambda index, report, cancel: index)
    assert [r.detail for r in results] == list(range(8))


# ---- Dialogs

def test_subtitle_option_needs_a_file(robot, messages, monkeypatch):
    monkeypatch.setattr(gui_helpers.filedialog, "askopenfilename", lambda **options: "/subs/film.fr.srt")
    robot.click("Hardcode")
    robot.click("OK")  # no file yet: an error, the window stays
    robot.click("Choose Subtitle File")
    robot.click("OK")
    assert gui_helpers.ask_subtitle_option("/videos/film.mkv") == ("hard", "/subs/film.fr.srt")
    assert [m[1] for m in messages] == ["Subtitle Error"]


def test_no_subtitles_and_closing(robot):
    robot.click("OK")
    assert gui_helpers.ask_subtitle_option("film.mkv") == ("none", None)
    robot.close()
    assert gui_helpers.ask_subtitle_option("film.mkv") is None


def test_videos_needing_subtitles(robot):
    robot.click("b.mkv")
    robot.click("OK")
    assert gui_helpers.ask_videos_needing_subtitles(["/v/a.mkv", "/v/b.mkv"]) == [False, True]
    robot.close()
    assert gui_helpers.ask_videos_needing_subtitles(["/v/a.mkv"]) is None


def test_the_gpu_h264_encoder_is_chosen_by_default(robot, monkeypatch):
    monkeypatch.setattr(encoders, "available_encoders",
                        lambda: [encoders.BY_NAME["h264_nvenc"], encoders.BY_NAME["libx264"], encoders.BY_NAME["libx265"]])
    robot.click("OK")
    assert gui_helpers.choose_encoder() is encoders.BY_NAME["h264_nvenc"]
    robot.click("HEVC")
    robot.click("OK")
    assert gui_helpers.choose_encoder() is encoders.BY_NAME["libx265"]


def test_container(robot):
    import gui_film
    robot.click("MKV")
    assert gui_film.ask_container() == "mkv"
    robot.close()
    assert gui_film.ask_container() is None


@pytest.fixture
def hdr_4k(monkeypatch):
    import gui_film
    monkeypatch.setattr(gui_film, "video_info", lambda path: (2160, True))
    monkeypatch.setattr(audio_codecs, "available_codecs", lambda: audio_codecs.CODECS)
    return gui_film


def test_compression_settings(robot, hdr_4k):
    for text in ("Fast", "720p", "Convert to SDR", "Opus", "128 kbps", "Keep the 5.1", "OK"):
        robot.click(text)
    settings = hdr_4k.ask_compression_settings(encoders.BY_NAME["libx265"], ["film.mkv"])
    assert (settings.speed, settings.max_height, settings.hdr_to_sdr, settings.audio_codec, settings.audio_kbps,
            settings.keep_surround) == ("fast", 720, True, "opus", 128, True)


def test_constant_quality(robot, hdr_4k):
    robot.read()
    robot.click("Constant quality, good")
    robot.click("OK")
    settings = hdr_4k.ask_compression_settings(encoders.BY_NAME["libx265"], ["film.mkv"])
    assert settings.quality == "good" and settings.speed == "balanced"
    assert "CRF/CQ 24" in robot.seen[0]


def test_copied_audio_has_no_bitrate_to_choose(robot, hdr_4k):
    robot.click("Keep the original audio")
    robot.do(lambda: robot.seen.append(robot.find("128 kbps").instate(["disabled"])))
    robot.click("OK")
    settings = hdr_4k.ask_compression_settings(encoders.BY_NAME["libx264"], ["film.mkv"])
    assert settings.audio_codec == COPY_AUDIO and robot.seen == [True]


def test_h264_explains_that_hdr_is_converted(robot, hdr_4k):
    robot.read()
    robot.close()
    assert hdr_4k.ask_compression_settings(encoders.BY_NAME["libx264"], ["film.mkv"]) is None
    assert "H.264 cannot keep the HDR" in robot.seen[0] and "1080p at most" in robot.seen[0]


def test_main_menu(robot):
    import main
    robot.click("Add subtitles")
    assert main.choose_usage_dialog() == "add_subtitles"


# ---- Workflows with their windows, the work replaced

def test_adding_subtitles_to_several_videos(robot, messages, monkeypatch):
    import gui_add_subtitles
    monkeypatch.setattr(gui_add_subtitles, "ask_video_files", lambda: ["/v/a.mkv", "/v/b.avi", "/v/c.mp4"])
    monkeypatch.setattr(gui_add_subtitles, "ask_subtitles_for",
                        lambda paths: [("soft", "a.srt"), ("none", None), ("hard", "c.srt")])
    done = []

    def add(path, option, sub_file, progress, cancel):
        progress(0.5)
        if path.endswith("c.mp4"):
            raise gui_add_subtitles.SubtitleError("Cannot read the subtitle file c.srt")
        done.append((path, option, sub_file))
        return path.replace(".mkv", "_with_subtitles.mkv")
    monkeypatch.setattr(gui_add_subtitles, "add_subtitles_to_video", add)
    gui_add_subtitles.run_add_subtitles_gui()
    assert done == [("/v/a.mkv", "soft", "a.srt")]  # b.avi has no subtitles to add
    # The failure is reported, not "All videos processed!"
    assert messages == [("error", "Adding subtitles failed",
                         "✔ a_with_subtitles.mkv\n\n✘ c.mp4 (hard):\nCannot read the subtitle file c.srt")]


def test_audio_conversion_window(robot, messages, monkeypatch):
    import gui_audio_conversion
    monkeypatch.setattr(audio_codecs, "available_codecs", lambda: audio_codecs.CODECS)
    monkeypatch.setattr(gui_audio_conversion, "ask_video_files", lambda: ["/v/film.mkv"])
    calls = []

    def convert(path, settings, progress, cancel):
        calls.append((path, settings))
        progress(1.0)
        return "/v/film_opus.mkv", ["FRE 6ch", "ENG 2ch"]
    monkeypatch.setattr(gui_audio_conversion, "run_audio_conversion", convert)
    for text in ("FLAC", "Opus", "Keep the channels", "Add Files", "Convert"):
        robot.click(text)
    robot.do(lambda: None, delay=1500)  # the conversion window closes 0.8 s after the end
    robot.read()
    robot.close()
    gui_audio_conversion.run_audio_conversion_gui()
    assert calls == [("/v/film.mkv", audio_codecs.AudioSettings("opus", 160, True))]
    assert "Finished: film_opus.mkv (audio tracks: FRE 6ch, ENG 2ch)" in robot.seen[0] and messages == []


def test_audio_tracks_management(robot, messages, monkeypatch):
    import gui_audio_tracks
    from audio_tracks import AudioTrackInfo, MediaFileInfo, SubtitleTrackInfo, VideoTrackInfo
    media = MediaFileInfo("/v/film.mkv", video_tracks=[VideoTrackInfo(0, "h264", 1920, 1080)],
                          audio_tracks=[AudioTrackInfo(1, "eng", codec="aac", channels=2, is_default=True),
                                        AudioTrackInfo(2, "fre", title="VFF", codec="ac3", channels=6)],
                          subtitle_tracks=[SubtitleTrackInfo(3, "fre", codec="subrip")], duration=10.0)
    monkeypatch.setattr(gui_audio_tracks.filedialog, "askopenfilename", lambda **options: "/v/film.mkv")
    monkeypatch.setattr(gui_audio_tracks, "ffprobe_streams", lambda path: media)
    commands = []

    def run(cmd, duration, report, cwd=None, cancel=None):
        commands.append(cmd)
        report(1.0)
    monkeypatch.setattr(gui_audio_tracks, "run_ffmpeg", run)
    robot.tree_click("1", "#1")  # the English track removed
    robot.tree_click("2", "#2")  # the French one by default
    robot.click("MKV")
    robot.click("Process")
    gui_audio_tracks.run_audio_tracks_gui()
    [cmd] = commands
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert maps == ["0:v", "0:a:1", "0:s:0"]  # the second audio track only
    assert cmd[cmd.index("-disposition:a:0") + 1] == "default" and cmd[-2].endswith("film_audio_processed.mkv")
    assert messages == [("info", "Audio tracks finished", "✔ film_audio_processed.mkv")]


def test_subtitle_translation_window(robot, messages, monkeypatch, tmp_path):
    import gui_subtitle
    subtitle = tmp_path / "film.en.srt"
    subtitle.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello.\n\n2\n00:00:03,000 --> 00:00:04,000\n"
                        "<i>Who's there?</i>\n", encoding="utf-8")
    monkeypatch.setattr(gui_subtitle.filedialog, "askopenfilenames", lambda **options: (str(subtitle),))
    monkeypatch.setattr(gui_subtitle, "show_message", lambda kind, title, text: messages.append((kind, title, text)))

    class FakeGoogle:
        def __init__(self, source, target):
            self.target = target

        def translate(self, text):
            return f"[{self.target}] {text}"
    monkeypatch.setattr(gui_subtitle, "GoogleTranslator", FakeGoogle)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.setattr(gui_subtitle.deepl, "KEY_FILE", str(tmp_path / "no_key.txt"))
    for text in ("Google Translate", "Browse Subtitles", "OK"):
        robot.click(text)
    gui_subtitle.run_subtitle_translation()
    translated = (tmp_path / "film.en_translated.srt").read_text(encoding="utf-8")
    assert "[fr] Hello." in translated and "[fr] <i>Who's there?</i>" in translated
    assert [(kind, title) for kind, title, _ in messages] == [("info", "Translation Complete")]
