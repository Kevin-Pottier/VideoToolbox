"""The compression workflow with its dialogs replaced by the answers of the user: no display needed."""
import threading

import pytest

import compression
import gui_film
import gui_helpers
from compression import CompressionSettings

SETTINGS = CompressionSettings(speed="fast", max_height=720, audio_kbps=128)


def run_jobs_here(title, names, work, done_text=None):
    """run_jobs without its window: the jobs one after the other in this thread."""
    return [gui_helpers.execute(name, work, index, lambda share: None, threading.Event())
            for index, name in enumerate(names)]


@pytest.fixture
def workflow(monkeypatch):
    """Runs run_video_compression with the given answers; returns the run_compression calls and the errors shown."""
    def run(files, subtitles=("none", None), container="mp4", encoder="libx264", size=1.5, failure=None,
            settings=SETTINGS):
        calls, errors = [], []

        def compress(*args, **kwargs):
            calls.append((args, {k: v for k, v in kwargs.items() if k not in ("progress", "cancel")}))
            if failure:
                raise compression.CompressionError(failure)
            return args[0].replace(".mkv", "_compressed.mp4")

        def message(kind, title, text):
            if kind == "error":
                errors.append(text)
        monkeypatch.setattr(gui_film, "ask_video_files", lambda: files)
        monkeypatch.setattr(gui_film, "ask_subtitles_for", lambda paths: None if subtitles is None
                            else [subtitles] * len(paths))
        monkeypatch.setattr(gui_film, "ask_container", lambda *args: container)
        monkeypatch.setattr(gui_film, "choose_encoder", lambda *args: encoder)
        monkeypatch.setattr(gui_film, "ask_compression_settings", lambda encoder, paths: settings)
        monkeypatch.setattr(gui_film, "ask_max_size", lambda *args: size)
        monkeypatch.setattr(gui_film, "run_compression", compress)
        monkeypatch.setattr(gui_film, "run_jobs", run_jobs_here)
        monkeypatch.setattr(gui_film, "show_message", message)
        monkeypatch.setattr(gui_helpers, "show_message", message)
        gui_film.run_video_compression()
        return calls, errors
    return run


def test_a_video_without_subtitles_is_compressed(workflow):
    calls, errors = workflow(("film.mkv",))
    assert calls == [(("film.mkv", "none", None, "mp4", 1.5), {"encoder": "libx264", "settings": SETTINGS})]
    assert errors == []


def test_the_subtitle_file_is_passed_on(workflow):
    calls, errors = workflow(("film.mkv",), subtitles=("soft", "film.srt"), container="mkv")
    assert calls == [(("film.mkv", "soft", "film.srt", "mkv", 1.5), {"encoder": "libx264", "settings": SETTINGS})]
    assert errors == []


@pytest.mark.parametrize("answers", [{"subtitles": None}, {"container": None}, {"encoder": None},
                                     {"settings": None}, {"size": None}])
def test_cancelling_a_dialog_compresses_nothing(workflow, answers):
    calls, _ = workflow(("film.mkv",), **answers)
    assert calls == []


def test_a_compression_error_is_shown_to_the_user(workflow):
    # It used to be printed in the console only: the window closed as if the compression had worked
    _, errors = workflow(("film.mkv",), failure="Target size too small")
    assert errors == ["✘ film.mkv:\nTarget size too small"]


def test_a_batch_compresses_every_video_and_reports_each_failure(workflow, monkeypatch):
    calls, errors = workflow(("a.mkv", "b.mkv"), container="mkv")
    assert [args[0] for args, _ in calls] == ["a.mkv", "b.mkv"] and errors == []
    calls, errors = workflow(("a.mkv", "b.mkv"), failure="ffmpeg failed")
    assert errors == ["✘ a.mkv:\nffmpeg failed\n\n✘ b.mkv:\nffmpeg failed"]


def test_no_file_chosen(workflow):
    calls, errors = workflow(())
    assert calls == []
    assert errors == ["No video files selected. Please choose at least one video file."]


def test_a_constant_quality_asks_no_size(workflow):
    quality = CompressionSettings(quality="good")
    calls, errors = workflow(("film.mkv",), settings=quality)
    assert calls == [(("film.mkv", "none", None, "mp4", None), {"encoder": "libx264", "settings": quality})]
