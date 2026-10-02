import os
import tkinter as tk
from tkinter import simpledialog, ttk

from colorama import Fore, Style

import audio_codecs
import encoders
from audio_tracks import ffprobe_streams
from compression import (AUDIO_BITRATE, AUDIO_CODECS, AUDIO_KBPS_CHOICES, COPY_AUDIO, MAX_HEIGHT_CHOICES,
                         CompressionSettings, run_compression)
from gui_helpers import (NOTE_FONT, app_root, ask_subtitles_for, ask_video_files, choose_encoder, create_styled_button,
                         create_styled_frame, create_styled_label, new_window, run_jobs, show_message, show_results)


def ask_container(title="Choose Output Container", prompt="Choose the output container:"):
    """Container dialog: returns "mp4" or "mkv", None if the window is closed."""
    win, frame = new_window(title, "300x170")
    create_styled_label(frame, prompt).pack(pady=10)
    result = {}

    def choose(ext):
        result["ext"] = ext
        win.destroy()
    create_styled_button(frame, "MP4", lambda: choose("mp4"), width=15).pack(pady=5)
    create_styled_button(frame, "MKV", lambda: choose("mkv"), width=15).pack(pady=5)
    win.wait_window()
    return result.get("ext")


GOAL_TEXTS = (
    ("size", "A target size, asked next (a limit: e-mail, Discord, USB key...): exact with x264/x265"),
    ("high", "Constant quality, high: no visible loss, the size the video needs"),
    ("good", "Constant quality, good: a much smaller file, a slight loss on close inspection"),
    ("small", "Constant quality, small: the smallest files, a visible loss"),
)
SPEED_TEXTS = {
    "fast": "Fast: about twice as fast, slightly lower quality",
    "balanced": "Balanced: the usual trade-off",
    "quality": "Best quality: 2 to 3 times slower, slightly better picture at the same size",
}


def video_info(path):
    """(height, HDR) of the video, (None, False) if it cannot be read."""
    try:
        media = ffprobe_streams(path)
    except (RuntimeError, OSError):
        return None, False
    if not media.video_tracks:
        return None, False
    return media.video_tracks[0].height, media.video_tracks[0].is_hdr


def ask_compression_settings(encoder, paths):
    """
    Settings dialog: a target size or a constant quality, speed (preset of the encoder), maximum height, audio,
    and what to do with HDR videos (when there is one). Only the heights below the tallest of the videos are
    offered.
    Returns a CompressionSettings, or None if the window is closed.
    """
    infos = [video_info(path) for path in paths]
    heights = [height for height, _ in infos if height]
    tallest = max(heights, default=None)
    any_hdr = any(is_hdr for _, is_hdr in infos)
    root, frame = new_window("Compression settings")
    goal = tk.StringVar(master=root, value="size")  # or a constant quality level (encoders.QUALITIES)
    speed = tk.StringVar(master=root, value="balanced")
    max_height = tk.IntVar(master=root, value=0)  # 0: the resolution is kept
    audio_codec = tk.StringVar(master=root, value="aac")
    audio_kbps = tk.IntVar(master=root, value=AUDIO_BITRATE // 1000)
    keep_surround = tk.BooleanVar(master=root, value=False)
    hdr_to_sdr = tk.BooleanVar(master=root, value=False)
    note = {"font": NOTE_FONT}

    create_styled_label(frame, "Size", style='Title.TLabel').pack(anchor="w")
    for value, text in GOAL_TEXTS:
        ttk.Radiobutton(frame, text=text, variable=goal, value=value, style='TRadiobutton').pack(anchor="w", padx=10)
    value = encoders.quality_value(encoder, "good")
    create_styled_label(frame, (f"Constant quality with {encoder.label}: CRF/CQ {value} for \"good\"." if value else
                                f"{encoder.label} has no constant quality scale: a bitrate following the resolution is "
                                "used.") + " The size of the files is not known in advance.", **note).pack(
        anchor="w", padx=10)

    create_styled_label(frame, "Speed / quality", style='Title.TLabel').pack(anchor="w", pady=(10, 0))
    for level in encoders.SPEEDS:
        preset = encoders.preset(encoder, level)
        ttk.Radiobutton(frame, text=SPEED_TEXTS[level] + (f" (preset {preset})" if preset else ""), variable=speed,
                        value=level, style='TRadiobutton').pack(anchor="w", padx=10)
    if not encoders.preset(encoder):
        create_styled_label(frame, f"{encoder.label} has no speed setting: the three are the same.", **note).pack(
            anchor="w", padx=10)

    create_styled_label(frame, "Resolution", style='Title.TLabel').pack(anchor="w", pady=(10, 0))
    keep = "Keep the resolution" + (f" ({tallest} lines)" if tallest and len(paths) == 1 else "")
    ttk.Radiobutton(frame, text=keep, variable=max_height, value=0, style='TRadiobutton').pack(anchor="w", padx=10)
    for height in MAX_HEIGHT_CHOICES:
        if tallest is None or height < tallest:
            ttk.Radiobutton(frame, text=f"{height}p at most", variable=max_height, value=height,
                            style='TRadiobutton').pack(anchor="w", padx=10)
    create_styled_label(frame, "For a small size, a lower resolution gives a sharper picture than a full resolution\n"
                               "starved of bitrate (smaller videos keep their own).", **note).pack(anchor="w", padx=10)

    if any_hdr:
        create_styled_label(frame, "HDR video", style='Title.TLabel').pack(anchor="w", pady=(10, 0))
        if encoder.codec == "H.264":
            create_styled_label(frame, "H.264 cannot keep the HDR: the video is converted to SDR (plays on every "
                                       "screen).\nChoose an HEVC or AV1 encoder to keep it.", **note).pack(anchor="w", padx=10)
        else:
            ttk.Radiobutton(frame, text="Keep the HDR (10 bits, for HDR screens and players)", variable=hdr_to_sdr,
                            value=False, style='TRadiobutton').pack(anchor="w", padx=10)
            ttk.Radiobutton(frame, text="Convert to SDR (plays on every screen)", variable=hdr_to_sdr, value=True,
                            style='TRadiobutton').pack(anchor="w", padx=10)
            create_styled_label(frame, "With burned subtitles the video is converted to SDR (they would be blinding "
                                       "in HDR).", **note).pack(anchor="w", padx=10)

    create_styled_label(frame, "Audio (every track is kept)", style='Title.TLabel').pack(anchor="w", pady=(10, 0))
    for codec in audio_codecs.available_codecs():
        if codec.name in AUDIO_CODECS:
            ttk.Radiobutton(frame, text=codec.label, variable=audio_codec, value=codec.name,
                            style='TRadiobutton').pack(anchor="w", padx=10)
    ttk.Radiobutton(frame, text="Keep the original audio (copied without loss, its real size is counted)",
                    variable=audio_codec, value=COPY_AUDIO, style='TRadiobutton').pack(anchor="w", padx=10)
    row = create_styled_frame(frame)
    row.pack(anchor="w", padx=10, pady=(4, 0))
    encoding_widgets = []
    for kbps in AUDIO_KBPS_CHOICES:
        button = ttk.Radiobutton(row, text=f"{kbps} kbps", variable=audio_kbps, value=kbps, style='TRadiobutton')
        button.pack(side="left", padx=(0, 8))
        encoding_widgets.append(button)
    surround = ttk.Checkbutton(frame, text="Keep the 5.1 / 7.1 surround (twice the bitrate for those tracks), "
                                           "instead of stereo", variable=keep_surround, style='TCheckbutton')
    surround.pack(anchor="w", padx=10, pady=(4, 0))
    encoding_widgets.append(surround)
    create_styled_label(frame, "Bitrate per stereo track: AAC 128 kbps is good, 192 kbps very good; Opus needs a third "
                               "less.", **note).pack(anchor="w", padx=10)

    def update_audio(*_args):
        # The original audio is copied: no bitrate, no channel choice
        for widget in encoding_widgets:
            widget.state(["disabled"] if audio_codec.get() == COPY_AUDIO else ["!disabled"])
    audio_codec.trace_add("write", update_audio)

    result = {}

    def ok():
        result["settings"] = CompressionSettings(speed.get(), max_height.get() or None, audio_kbps.get(),
                                                 keep_surround.get(), audio_codec.get(), hdr_to_sdr.get(),
                                                 None if goal.get() == "size" else goal.get())
        root.destroy()
    create_styled_button(frame, "OK", ok, width=12).pack(pady=(12, 0))
    root.wait_window()
    return result.get("settings")


def ask_max_size(title="Target Video Size", prompt="Enter the maximum file size in GB:"):
    """Asks for the target size in GB until it is valid; returns None if the dialog is cancelled."""
    while True:
        size_input = simpledialog.askstring(title, prompt, parent=app_root())
        if size_input is None:
            return None
        try:
            max_size_gb = float(size_input)
        except ValueError:
            max_size_gb = None
        if max_size_gb is not None and max_size_gb > 0:
            return max_size_gb
        show_message("error", "Size Error", "Invalid size. Must be greater than 0.")


def run_video_compression():
    """
    Compression of one or more videos: subtitles of each one, container, encoder, settings and target size
    (the same for all), then the compressions in parallel with a progress window, and a message at the end.
    """
    paths = ask_video_files()
    if not paths:
        show_message("error", "File Error", "No video files selected. Please choose at least one video file.")
        return
    several = len(paths) > 1
    # Subtitles: (option, file), file None when the video is compressed without subtitles
    subtitles = ask_subtitles_for(paths)
    if subtitles is None:
        return
    ext = (ask_container("Choose Output Container (Multiple)", "Choose the output container (applies to all):")
           if several else ask_container())
    if ext not in ("mp4", "mkv"):
        print(Fore.RED + "No container selected. Aborting." + Style.RESET_ALL)
        return
    encoder = choose_encoder()
    if encoder is None:
        print(Fore.RED + "No encoder selected. Aborting." + Style.RESET_ALL)
        return
    settings = ask_compression_settings(encoder, paths)
    if settings is None:
        print(Fore.RED + "No settings chosen. Aborting." + Style.RESET_ALL)
        return
    if settings.quality:
        max_size_gb = None  # constant quality: the size the video needs
    else:
        max_size_gb = (ask_max_size("Target Video Size (Multiple)", "Enter the maximum file size in GB (applies to all):")
                       if several else ask_max_size())
        if max_size_gb is None:
            return

    def compress(index, report, cancel):
        sub_option, sub_file = subtitles[index]
        return run_compression(paths[index], sub_option, sub_file, ext, max_size_gb, progress=report, encoder=encoder,
                               settings=settings, cancel=cancel)
    results = run_jobs("Compression", [os.path.basename(path) for path in paths], compress, done_text=describe_output)
    show_results("Compression", results, describe_output)
    done = sum(result.ok for result in results)
    print((Fore.GREEN if done == len(paths) else Fore.RED)
          + f"\nCompression complete: {done}/{len(paths)} file(s) compressed." + Style.RESET_ALL)


def describe_output(path):
    """'film_compressed.mkv (712.4 MB)'"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return os.path.basename(path)
    return f"{os.path.basename(path)} ({size / 1024 ** 2:.1f} MB)"
