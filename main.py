from gui_helpers import close_app, create_styled_button, create_styled_label, new_window


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
    root, frame = new_window("VideoCompress - Main Menu", "380x420")
    create_styled_label(frame, "VideoCompress", style='Title.TLabel').pack(pady=(18, 2))
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
        run(choose_usage_dialog())
    finally:
        close_app()


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
    main()
