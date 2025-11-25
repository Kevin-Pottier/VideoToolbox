"""
gui_audio_fix.py
-----------------

This script provides a graphical user interface (GUI) for down‑mixing the
audio track of one or more video files to stereo AAC using the
``audio_fix`` module.  It leverages the shared ``gui_helpers`` module
from this repository to deliver a consistent look and feel across
different tools.  Users can select multiple files, launch the
conversion and track progress for each file via a progress bar and
status label.

Usage:

    python gui_audio_fix.py

On launch, a window will appear allowing you to browse for video
files (MP4/MKV).  Once files are selected, click "Convert" to
start processing.  A secondary window will display individual
progress bars for each file.  Upon completion, output files named
``*_fixed.ext`` will be written alongside the originals.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from tkinter import scrolledtext
from typing import Callable, Optional

from audio_fix import run_audio_fix
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button

def gui_audio() -> None:
    # Root window setup
    root = tk.Tk()
    root.title("Audio Fix (Stereo Down‑mix)")
    root.geometry("520x400")
    root.attributes('-topmost', True)
    style = ttk.Style(root)
    apply_modern_theme(root, style)

    files_to_process: list[str] = []

    # Containers
    frame = create_styled_frame(root)
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    create_styled_label(frame, text="Audio Fix (Stereo Down‑mix)", style='Title.TLabel').pack(pady=(0, 8))

    # File list display
    list_frame = create_styled_frame(frame)
    list_frame.pack(fill="both", expand=True, pady=(0, 8))
    listbox_files = tk.Listbox(list_frame, selectmode=tk.BROWSE, bg="#2f343f", fg="#f5f6fa", highlightthickness=0)
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
        root.attributes('-topmost', True)
        filepaths = filedialog.askopenfilenames(
            title="Choose video file(s)",
            filetypes=[("Videos", "*.mp4 *.mkv"), ("All files", "*.*")]
        )
        if not filepaths:
            return
        # Clear existing list before adding new entries
        files_to_process.clear()
        listbox_files.delete(0, tk.END)
        for p in root.tk.splitlist(filepaths):
            files_to_process.append(p)
            listbox_files.insert(tk.END, os.path.basename(p))
        append_log(f"Selected {len(files_to_process)} file(s) for audio fix.")

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
        # Create progress window
        progress_win = tk.Toplevel(root)
        progress_win.title("Batch Audio Fix Progress")
        progress_win.geometry(f"500x{120 + 60 * len(files_to_process)}")
        apply_modern_theme(progress_win)
        batch_frame = create_styled_frame(progress_win)
        batch_frame.pack(fill="both", expand=True, padx=10, pady=10)
        create_styled_label(batch_frame, text="Batch Audio Fix Progress", style='Title.TLabel').pack(pady=(0, 8))
        progress_vars: list[tk.DoubleVar] = []
        progress_bars: list[ttk.Progressbar] = []
        status_labels: list[tk.Widget] = []
        for p in files_to_process:
            filename = os.path.basename(p)
            create_styled_label(batch_frame, text=filename, anchor="w").pack(anchor="w")
            pvar = tk.DoubleVar(value=0)
            pbar = ttk.Progressbar(batch_frame, variable=pvar, maximum=100, length=420, style='TProgressbar')
            pbar.pack(pady=(0, 2))
            slabel = create_styled_label(batch_frame, text="Waiting...", style='TLabel', font=("Segoe UI", 9, "italic"))
            slabel.pack(anchor="w", pady=(0, 8))
            progress_vars.append(pvar)
            progress_bars.append(pbar)
            status_labels.append(slabel)

        def on_file_done(idx: int, input_path: str, success: bool, error: Optional[Exception] = None) -> None:
            def finish() -> None:
                if success:
                    status_labels[idx].config(text="Done!")
                    append_log(f"Finished: {os.path.basename(input_path)}")
                else:
                    status_labels[idx].config(text="Error")
                    append_log(f"Error processing {os.path.basename(input_path)}: {error}")
                # If all finished, re‑enable buttons and close progress window
                if all(status_labels[i].cget("text") in ("Done!", "Error") for i in range(len(files_to_process))):
                    convert_btn.config(state="normal")
                    add_btn.config(state="normal")
                    clear_btn.config(state="normal")
                    progress_win.destroy()
            root.after(0, finish)

        def make_progress_callback(idx: int) -> Callable[[float, Optional[int], Optional[int]], None]:
            def callback(percent: float, mins: Optional[int], secs: Optional[int]) -> None:
                try:
                    progress_vars[idx].set(percent)
                    if mins is not None and secs is not None:
                        status_labels[idx].config(text=f"{percent:5.1f}% | ETA: {mins:02d}:{secs:02d}")
                    else:
                        status_labels[idx].config(text=f"{percent:5.1f}% | ETA: --:--")
                except Exception:
                    pass
            return callback

        # Launch conversions in parallel (one thread per file)
        def worker(idx: int, path: str) -> None:
            try:
                run_audio_fix(path, gui_progress=make_progress_callback(idx))
                on_file_done(idx, path, True)
            except Exception as e:
                on_file_done(idx, path, False, e)

        for i, path in enumerate(files_to_process):
            threading.Thread(target=worker, args=(i, path), daemon=True).start()

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
