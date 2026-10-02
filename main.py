"""
VideoToolbox: python main.py opens the main menu; python main.py --check (or VideoToolbox.exe --check) checks the
installation: the modules, Real-ESRGAN and its models, FFmpeg and the windows.
"""
import sys

from gui_helpers import close_app, create_styled_button, create_styled_label, new_window, show_message
from utils import ffmpeg_install_hint, missing_ffmpeg_tools
from version import VERSION

# The modules of the features, imported when chosen in the menu (checked by --check)
FEATURE_MODULES = ("gui_film", "gui_subtitle", "gui_upscale", "gui_audio_conversion", "gui_add_subtitles",
                   "gui_audio_tracks")


def choose_usage_dialog():
    """
    Display a GUI window for the user to choose the main usage mode of the script.
    Returns:
        str: 'video_compression', 'sub_translation', or 'video_upscale' depending on user choice.
    """
    usage = None

    def set_usage(val):
        nonlocal usage
        usage = val
        root.destroy()
    root, frame = new_window("VideoToolbox - Main Menu", "380x420")
    create_styled_label(frame, "VideoToolbox" + ("" if VERSION == "dev" else f" {VERSION}"),
                        style='Title.TLabel').pack(pady=(18, 2))
    create_styled_label(frame, "Choose how to use this script:").pack(pady=(0, 16))
    create_styled_button(frame, "Video Compression", lambda: set_usage("video_compression"), width=22).pack(pady=7)
    create_styled_button(frame, "Subtitle Translation", lambda: set_usage("sub_translation"), width=22).pack(pady=7)
    create_styled_button(frame, "Upscale video (Real-ESRGAN)", lambda: set_usage("video_upscale"), width=22).pack(pady=7)
    create_styled_button(frame, "Audio conversion", lambda: set_usage("audio_conversion"), width=22).pack(pady=7)
    create_styled_button(frame, "Add subtitles", lambda: set_usage("add_subtitles"), width=22).pack(pady=7)
    create_styled_button(frame, "Audio Tracks Management", lambda: set_usage("audio_tracks"), width=22).pack(pady=7)
    root.wait_window()
    return usage


def main():
    """
    Main entry point for the script. Runs the selected workflow based on user choice.
    """
    try:
        missing = missing_ffmpeg_tools()
        if missing:
            show_message("warning", "FFmpeg not found",
                         f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not in the PATH: the compression, "
                         "the upscaling and the audio and subtitle tools need FFmpeg (the subtitle translation does "
                         f"not).\n\nInstall it with:\n{ffmpeg_install_hint()}\n\nthen start VideoToolbox again.")
        run(choose_usage_dialog())
    finally:
        close_app()


def check():
    """
    Check the installation (or the .exe built by PyInstaller): every module imports, Real-ESRGAN and its models
    are there, FFmpeg is found, a window opens. Prints the result; returns the exit code (1 if the application
    itself is incomplete; FFmpeg, installed apart, is only reported).
    """
    import importlib
    import os
    import subprocess
    problems = []
    print(f"VideoToolbox {VERSION}, Python {sys.version.split()[0]}"
          + (", executable built by PyInstaller" if getattr(sys, "frozen", False) else ""))
    for name in FEATURE_MODULES:
        try:
            importlib.import_module(name)
        except Exception as e:  # a module or a dependency missing from the build
            problems.append(f"module {name}: {type(e).__name__}: {e}")
    print(f"Modules: {'ok' if not problems else 'MISSING'}")
    import gui_upscale
    files = [gui_upscale.REALESRGAN_EXE] + [
        os.path.join(gui_upscale.TOOL_DIR, "models", f"{model.name}{'' if len(model.scales) == 1 else f'-x{scale}'}{ext}")
        for model in gui_upscale.MODELS for scale in model.scales for ext in (".param", ".bin")]
    absent = [path for path in files if not os.path.isfile(path)]
    problems += [f"missing: {path}" for path in absent]
    print(f"Real-ESRGAN and its {len(files) - 1} model files: {'ok' if not absent else 'MISSING'} ({gui_upscale.TOOL_DIR})")
    missing = missing_ffmpeg_tools()
    if missing:
        print(f"FFmpeg: {' and '.join(missing)} not found in the PATH. Install it with:\n  {ffmpeg_install_hint()}")
    else:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, encoding="utf-8",
                             errors="replace").stdout
        print(f"FFmpeg: {out.splitlines()[0] if out else 'found'}")
    import tkinter as tk
    try:
        tk.Tk().destroy()
        print("Windows (Tk): ok")
    except tk.TclError as e:
        problems.append(f"Tk: {e}")
        print(f"Windows (Tk): FAILED ({e})")
    for problem in problems:
        print(f"  {problem}")
    print("Check passed." if not problems else "Check FAILED.")
    return 1 if problems else 0


def run(usage):
    if usage == "video_compression":
        from gui_film import run_video_compression
        run_video_compression()
    elif usage == "sub_translation":
        from gui_subtitle import run_subtitle_translation
        run_subtitle_translation()
    elif usage == "video_upscale":
        from gui_upscale import run_video_upscale_gui
        run_video_upscale_gui()
    elif usage == "audio_conversion":
        from gui_audio_conversion import run_audio_conversion_gui
        run_audio_conversion_gui()
    elif usage == "add_subtitles":
        from gui_add_subtitles import run_add_subtitles_gui
        run_add_subtitles_gui()
    elif usage == "audio_tracks":
        from gui_audio_tracks import run_audio_tracks_gui
        run_audio_tracks_gui()


if __name__ == "__main__":
    sys.exit(check()) if "--check" in sys.argv[1:] else main()
