"""The compression workflow with its dialogs replaced by the answers of the user: no display needed."""
import pytest

import gui_film
from compression import CompressionSettings

SETTINGS = CompressionSettings(speed="fast", max_height=720, audio_kbps=128)


@pytest.fixture
def workflow(monkeypatch):
    """Runs run_video_compression with the given answers; returns the run_compression calls and the errors shown."""
    def run(files, subtitles=("none", None), container="mp4", encoder="libx264", size=1.5, failure=None,
            settings=SETTINGS):
        calls, errors = [], []

        def compress(*args, **kwargs):
            calls.append((args, kwargs))
            if failure:
                raise gui_film.CompressionError(failure)
        monkeypatch.setattr(gui_film, "ask_video_files", lambda: files)
        monkeypatch.setattr(gui_film, "ask_subtitles", lambda path: subtitles)
        monkeypatch.setattr(gui_film, "ask_container", lambda *args: container)
        monkeypatch.setattr(gui_film, "choose_encoder", lambda *args: encoder)
        monkeypatch.setattr(gui_film, "ask_compression_settings", lambda encoder, paths: settings)
        monkeypatch.setattr(gui_film, "ask_max_size", lambda *args: size)
        monkeypatch.setattr(gui_film, "run_compression", compress)
        monkeypatch.setattr(gui_film, "show_message", lambda kind, title, message: errors.append(message))
        monkeypatch.setattr(gui_film.messagebox, "showerror", lambda title, message, **kwargs: errors.append(message))
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


@pytest.mark.parametrize("answers", [{"encoder": None}, {"settings": None}, {"size": None}])
def test_cancelling_a_dialog_compresses_nothing(workflow, answers):
    calls, _ = workflow(("film.mkv",), **answers)
    assert calls == []


def test_a_compression_error_is_shown_to_the_user(workflow):
    # It used to be printed in the console only: the window closed as if the compression had worked
    _, errors = workflow(("film.mkv",), failure="Target size too small")
    assert errors == ["film.mkv:\nTarget size too small"]


def test_no_file_chosen(workflow):
    calls, errors = workflow(())
    assert calls == []
    assert errors == ["No video files selected. Please choose at least one video file."]
