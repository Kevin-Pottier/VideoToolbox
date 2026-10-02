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
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from tkinter import scrolledtext
from typing import Callable, Optional

import audio_codecs
from audio_codecs import AudioSettings
from audio_conversion import run_audio_conversion
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button


def run_audio_conversion_gui() -> None:
    # Root window setup
    root = tk.Tk()
    root.title("Audio conversion")
    root.attributes('-topmost', True)
    style = ttk.Style(root)
    apply_modern_theme(root, style)

    files_to_process: list[str] = []

    # Containers
    frame = create_styled_frame(root)
    frame.pack(fill="both", expand=True, padx=10, pady=10)

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
        root.lift()
        root.attributes("-topmost", True)
        filepaths = filedialog.askopenfilenames(
            title="Choose video file(s)",
            filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.m4v *.ts *.wmv *.flv"), ("All files", "*.*")]
        )

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
            msg_root = tk.Toplevel(root)
            msg_root.withdraw()
            messagebox.showerror("File Error", "No video file(s) selected.", parent=msg_root)
            msg_root.destroy()
            return
        # Disable buttons during conversion
        convert_btn.config(state="disabled")
        add_btn.config(state="disabled")
        clear_btn.config(state="disabled")
        settings = AudioSettings(codec_var.get(), kbps_var.get(), surround_var.get())
        append_log(f"Converting to {settings.codec.upper()}"
                   + ("" if audio_codecs.BY_NAME[settings.codec].lossless else f" at {settings.kbps} kbps")
                   + (", channels kept." if settings.keep_surround else ", stereo."))
        # Create progress window
        progress_win = tk.Toplevel(root)
        progress_win.title("Audio Conversion Progress")
        progress_win.geometry(f"500x{120 + 60 * len(files_to_process)}")
        apply_modern_theme(progress_win)
        batch_frame = create_styled_frame(progress_win)
        batch_frame.pack(fill="both", expand=True, padx=10, pady=10)
        create_styled_label(batch_frame, text="Audio Conversion Progress", style='Title.TLabel').pack(pady=(0, 8))
        progress_vars: list[tk.DoubleVar] = []
        progress_bars: list[ttk.Progressbar] = []
        status_labels: list[tk.Label] = []
        for p in files_to_process:
            filename = os.path.basename(p)
            create_styled_label(batch_frame, text=filename, anchor="w").pack(anchor="w")
            pvar = tk.DoubleVar(value=0, master=progress_win)
            pbar = ttk.Progressbar(batch_frame, variable=pvar, maximum=100, length=420, style='TProgressbar')
            pbar.pack(pady=(0, 2))
            slabel = create_styled_label(batch_frame, text="Waiting...", style='TLabel', font=("Segoe UI", 9, "italic"))
            slabel.pack(anchor="w", pady=(0, 8))
            progress_vars.append(pvar)
            progress_bars.append(pbar)
            status_labels.append(slabel)

        # The worker threads never touch Tk: they fill this queue, applied by poll() in the Tk thread
        events: "queue.Queue[tuple]" = queue.Queue()

        def on_file_done(idx: int, input_path: str, success: bool, error: Optional[Exception] = None,
                         result: Optional[tuple] = None) -> None:
            events.put(("done", idx, input_path, success, error, result))

        def finish(idx: int, input_path: str, success: bool, error: Optional[Exception],
                   result: Optional[tuple]) -> bool:
            """Show the result of one file; True once every file is finished."""
            if success:
                output_file, track_order = result
                status_labels[idx].config(text="Done!")
                append_log(f"Finished: {os.path.basename(output_file)} (audio tracks: {', '.join(track_order)})")
            else:
                status_labels[idx].config(text="Error")
                append_log(f"Error processing {os.path.basename(input_path)}: {error}")
            return all(status_labels[i].cget("text") in ("Done!", "Error") for i in range(len(files_to_process)))

        def make_progress_callback(idx: int) -> Callable[[float, Optional[int], Optional[int]], None]:
            def callback(percent: float, mins: Optional[int], secs: Optional[int]) -> None:
                events.put(("progress", idx, percent, mins, secs))
            return callback

        def show_progress(idx: int, percent: float, mins: Optional[int], secs: Optional[int]) -> None:
            progress_vars[idx].set(percent)
            eta = f"{mins:02d}:{secs:02d}" if mins is not None and secs is not None else "--:--"
            status_labels[idx].config(text=f"{percent:5.1f}% | ETA: {eta}")

        def poll() -> None:
            try:
                while True:
                    event = events.get_nowait()
                    if event[0] == "progress":
                        show_progress(*event[1:])
                    elif finish(*event[1:]):
                        # Every file is finished: re‑enable the buttons and close the progress window
                        convert_btn.config(state="normal")
                        add_btn.config(state="normal")
                        clear_btn.config(state="normal")
                        progress_win.destroy()
                        return
            except queue.Empty:
                pass
            root.after(200, poll)

        # Launch conversions in parallel (one thread per file)
        def worker(idx: int, path: str) -> None:
            try:
                result = run_audio_conversion(path, settings, gui_progress=make_progress_callback(idx))
                on_file_done(idx, path, True, result=result)
            except Exception as e:
                on_file_done(idx, path, False, e)

        for i, path in enumerate(files_to_process):
            threading.Thread(target=worker, args=(i, path), daemon=True).start()
        poll()

    # Buttons
    btn_frame = create_styled_frame(frame)
    btn_frame.pack(pady=8)
    add_btn = create_styled_button(btn_frame, text="Add Files", command=add_files, width=14)
    add_btn.pack(side="left", padx=4)
    convert_btn = create_styled_button(btn_frame, text="Convert", command=convert_files, width=12)
    convert_btn.pack(side="left", padx=4)
    clear_btn = create_styled_button(btn_frame, text="Clear List", command=clear_list, width=14)
    clear_btn.pack(side="left", padx=4)

    root.mainloop()
