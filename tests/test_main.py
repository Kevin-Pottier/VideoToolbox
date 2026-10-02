"""The entry point: the FFmpeg warning at the start, and the check of the installation (main.py --check)."""
import os

import pytest

import main


@pytest.fixture
def started(monkeypatch):
    """Runs main.main() with the menu closed; returns the messages shown."""
    shown = []
    monkeypatch.setattr(main, "show_message", lambda kind, title, text: shown.append((kind, title, text)))
    monkeypatch.setattr(main, "choose_usage_dialog", lambda: None)
    return shown


def test_a_missing_ffmpeg_is_announced_at_the_start(started, monkeypatch):
    monkeypatch.setattr(main, "missing_ffmpeg_tools", lambda: ["ffmpeg", "ffprobe"])
    monkeypatch.setattr(main.sys, "platform", "win32")
    main.main()
    [(kind, title, text)] = started
    assert (kind, title) == ("warning", "FFmpeg not found")
    assert text.startswith("ffmpeg and ffprobe are not in the PATH") and "winget install Gyan.FFmpeg" in text


def test_nothing_is_said_when_ffmpeg_is_there(started, monkeypatch):
    monkeypatch.setattr(main, "missing_ffmpeg_tools", lambda: [])
    main.main()
    assert started == []


def test_the_check_reports_a_missing_model(monkeypatch, tmp_path, capsys):
    import gui_upscale
    (tmp_path / "models").mkdir()
    exe = tmp_path / os.path.basename(gui_upscale.REALESRGAN_EXE)
    exe.write_bytes(b"")
    for name in ("realesrgan-x4plus", "realesr-animevideov3-x2", "realesr-animevideov3-x3"):  # x4 missing
        for ext in (".param", ".bin"):
            (tmp_path / "models" / f"{name}{ext}").write_bytes(b"")
    monkeypatch.setattr(gui_upscale, "TOOL_DIR", str(tmp_path))
    monkeypatch.setattr(gui_upscale, "REALESRGAN_EXE", str(exe))
    monkeypatch.setattr(main, "missing_ffmpeg_tools", lambda: ["ffmpeg"])
    import tkinter
    monkeypatch.setattr(tkinter, "Tk", lambda: type("Root", (), {"destroy": lambda self: None})())
    assert main.check() == 1
    out = capsys.readouterr().out
    assert "Modules: ok" in out and "8 model files: MISSING" in out and "realesr-animevideov3-x4.bin" in out
    assert "FFmpeg: ffmpeg not found" in out and out.rstrip().endswith("Check FAILED.")
