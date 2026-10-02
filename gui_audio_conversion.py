"""
gui_audio_conversion.py
-----------------------

Window of the audio conversion (see the audio_conversion module): choose one or more videos, the codec
(AAC, Opus, AC3, E-AC3, FLAC: the ones of this ffmpeg build), the bitrate per track and stereo or the
5.1/7.1 channels kept, then "Convert". The video is not re-encoded; every track is kept, French tracks
first. A second window shows the progress of each file; the outputs (*_aac.mkv, *_opus.mp4...) are written
next to the originals.
"""

import os
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext

import audio_codecs
from audio_codecs import AudioSettings
from audio_conversion import run_audio_conversion
from gui_helpers import (ask_video_files, create_styled_button, create_styled_frame, create_styled_label, new_window,
                         run_jobs, show_message, show_results)


def run_audio_conversion_gui() -> None:
    root, frame = new_window("Audio conversion")
    files_to_process: list[str] = []

    create_styled_label(frame, text="Audio conversion (the video is not re-encoded)", style='Title.TLabel').pack(
        pady=(0, 8))

    # Settings: codec, bitrate per track, channels
    defaults = AudioSettings()
    codec_var = tk.StringVar(master=root, value=defaults.codec)
    kbps_var = tk.IntVar(master=root, value=defaults.kbps)
    surround_var = tk.BooleanVar(master=root, value=defaults.keep_surround)
    note = {"font": ("Segoe UI", 9, "italic")}
    settings_frame = create_styled_frame(frame)
    settings_frame.pack(fill="x", pady=(0, 8))
    create_styled_label(settings_frame, "Codec").pack(anchor="w")
    for codec in audio_codecs.available_codecs():
        ttk.Radiobutton(settings_frame, text=codec.label, variable=codec_var, value=codec.name,
                        style='TRadiobutton').pack(anchor="w", padx=10)
    create_styled_label(settings_frame, "Bitrate per stereo track (5.1/7.1 tracks kept: twice)").pack(
        anchor="w", pady=(6, 0))
    kbps_row = create_styled_frame(settings_frame)
    kbps_row.pack(anchor="w", padx=10)
    kbps_buttons = []
    for kbps in audio_codecs.KBPS_CHOICES:
        button = ttk.Radiobutton(kbps_row, text=f"{kbps} kbps", variable=kbps_var, value=kbps, style='TRadiobutton')
        button.pack(side="left", padx=(0, 8))
        kbps_buttons.append(button)
    create_styled_label(settings_frame, "Opus: 96 to 128 kbps are enough; AAC, AC3: 160 to 192 kbps.", **note).pack(
        anchor="w", padx=10)
    create_styled_label(settings_frame, "Channels").pack(anchor="w", pady=(6, 0))
    ttk.Radiobutton(settings_frame, text="Stereo (down-mix of the 5.1/7.1 tracks)", variable=surround_var,
                    value=False, style='TRadiobutton').pack(anchor="w", padx=10)
    ttk.Radiobutton(settings_frame, text="Keep the channels (5.1, 7.1...; AC3/E-AC3: 5.1 at most)",
                    variable=surround_var, value=True, style='TRadiobutton').pack(anchor="w", padx=10)

    def update_kbps(*_args) -> None:
        # FLAC is lossless: no bitrate to choose
        state = ["disabled"] if audio_codecs.BY_NAME[codec_var.get()].lossless else ["!disabled"]
        for button in kbps_buttons:
            button.state(state)
    codec_var.trace_add("write", update_kbps)

    # File list display
    list_frame = create_styled_frame(frame)
    list_frame.pack(fill="both", expand=True, pady=(0, 8))
    listbox_files = tk.Listbox(list_frame, selectmode=tk.BROWSE, height=5, bg="#2f343f", fg="#f5f6fa",
                               highlightthickness=0)
    listbox_files.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar_list = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox_files.yview)
    scrollbar_list.pack(side=tk.RIGHT, fill=tk.Y)
    listbox_files.configure(yscrollcommand=scrollbar_list.set)

    # Log area
    log_frame = create_styled_frame(frame)
    log_frame.pack(fill="both", expand=True, pady=(0, 8))
    log_text = scrolledtext.ScrolledText(log_frame, height=6, bg="#2f343f", fg="#f5f6fa", wrap=tk.WORD)
    log_text.pack(fill="both", expand=True)

    def append_log(message: str) -> None:
        log_text.insert(tk.END, message + "\n")
        log_text.see(tk.END)

    # Button commands
    def add_files() -> None:
        filepaths = ask_video_files()
        if not filepaths:
            return

        files_to_process.clear()
        listbox_files.delete(0, tk.END)

        for p in filepaths:
            files_to_process.append(p)
            listbox_files.insert(tk.END, os.path.basename(p))

        append_log(f"Selected {len(files_to_process)} file(s) for the audio conversion.")

    def clear_list() -> None:
        files_to_process.clear()
        listbox_files.delete(0, tk.END)
        append_log("Cleared file list.")

    def convert_files() -> None:
        if not files_to_process:
            show_message("error", "File Error", "No video file(s) selected.")
            return
        settings = AudioSettings(codec_var.get(), kbps_var.get(), surround_var.get())
        append_log(f"Converting to {settings.codec.upper()}"
                   + ("" if audio_codecs.BY_NAME[settings.codec].lossless else f" at {settings.kbps} kbps")
                   + (", channels kept." if settings.keep_surround else ", stereo."))
        paths = list(files_to_process)

        def convert(index, report, cancel):
            return run_audio_conversion(paths[index], settings, progress=report, cancel=cancel)
        # The buttons are disabled meanwhile: the conversion window waits in this callback
        buttons = (convert_btn, add_btn, clear_btn)
        for button in buttons:
            button.state(["disabled"])
        try:
            results = run_jobs("Audio conversion", [os.path.basename(path) for path in paths], convert,
                               done_text=lambda result: os.path.basename(result[0]))
        finally:
            for button in buttons:
                if button.winfo_exists():
                    button.state(["!disabled"])
        for result in results:
            if result.ok:
                output_file, track_order = result.detail
                append_log(f"Finished: {os.path.basename(output_file)} (audio tracks: {', '.join(track_order)})")
            else:
                append_log(f"Error processing {result.name}: {result.detail}")
        if not all(result.ok for result in results):
            show_results("Audio conversion", results, lambda result: os.path.basename(result[0]))

    # Buttons
    btn_frame = create_styled_frame(frame)
    btn_frame.pack(pady=8)
    add_btn = create_styled_button(btn_frame, text="Add Files", command=add_files, width=14)
    add_btn.pack(side="left", padx=4)
    convert_btn = create_styled_button(btn_frame, text="Convert", command=convert_files, width=12)
    convert_btn.pack(side="left", padx=4)
    clear_btn = create_styled_button(btn_frame, text="Clear List", command=clear_list, width=14)
    clear_btn.pack(side="left", padx=4)

    root.wait_window()
