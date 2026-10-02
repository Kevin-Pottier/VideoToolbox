import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, ttk
from colorama import Fore, Style
import os
import audio_codecs
import encoders
from audio_tracks import ffprobe_streams
from compression import (AUDIO_BITRATE, AUDIO_CODECS, AUDIO_KBPS_CHOICES, COPY_AUDIO, MAX_HEIGHT_CHOICES,
                         CompressionError, CompressionSettings, run_compression)
from gui_helpers import (apply_modern_theme, choose_encoder, create_styled_button, create_styled_frame,
                         create_styled_label, show_message)


def ask_video_files():
    """File picker for one or more videos; returns the chosen paths (empty if cancelled)."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_paths = filedialog.askopenfilenames(title="Choose video file(s)", filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv")])
    root.destroy()
    return file_paths


def ask_subtitles(path):
    """
    Subtitle dialog for one video. Returns (option, file): option is "none", "soft" or "hard",
    file is None for "none". For "soft" and "hard" the dialog comes back until a file is chosen.
    """
    sub_option = None
    sub_file = None
    while sub_option is None or (sub_option in ("soft", "hard") and not sub_file):
        sub_root = tk.Tk()
        sub_root.attributes('-topmost', True)
        sub_option_var = tk.StringVar(value="none", master=sub_root)
        sub_file_var = tk.StringVar(value="", master=sub_root)
        sub_root.title(f"Subtitle Options for {os.path.basename(path)}")
        sub_root.geometry("400x300")
        sub_root.configure(bg="#23272e")
        apply_modern_theme(sub_root)
        frame = create_styled_frame(sub_root)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        create_styled_label(frame, f"Subtitle options for:\n{os.path.basename(path)}").pack(pady=5)
        def toggle_sub():
            if sub_option_var.get() == "none":
                sub_btn.state(["disabled"])
                sub_file_var.set("")
            else:
                sub_btn.state(["!disabled"])
        ttk.Radiobutton(frame, text="No subtitles", variable=sub_option_var, value="none", command=toggle_sub, style='TRadiobutton').pack(anchor="w", padx=40)
        ttk.Radiobutton(frame, text="Softcode (attach .srt)", variable=sub_option_var, value="soft", command=toggle_sub, style='TRadiobutton').pack(anchor="w", padx=40)
        ttk.Radiobutton(frame, text="Hardcode (burn in)", variable=sub_option_var, value="hard", command=toggle_sub, style='TRadiobutton').pack(anchor="w", padx=40)
        sub_btn = create_styled_button(frame, "Choose Subtitle File", lambda: sub_file_var.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]) or sub_file_var.get()))
        sub_btn.pack(pady=5)
        sub_btn.state(["disabled"])
        sub_label = create_styled_label(frame, "", textvariable=sub_file_var)
        sub_label.pack(pady=5)
        def ok():
            sub_root.quit()
        create_styled_button(frame, "OK", ok).pack(pady=10)
        sub_root.after(100, toggle_sub)
        sub_root.mainloop()
        sub_option = sub_option_var.get()
        sub_file = sub_file_var.get() if sub_file_var.get() else None
        sub_root.destroy()
        if sub_option in ("soft", "hard") and not sub_file:
            show_message("error", "Subtitle Error", "You selected a subtitle option but did not choose a subtitle file. Please choose a subtitle file.")
    return sub_option, sub_file


def ask_container(title="Choose Output Container", prompt="Choose the output container:"):
    """Container dialog: returns "mp4" or "mkv"."""
    container_root = tk.Tk()
    container_root.withdraw()
    container_root.attributes('-topmost', True)
    container_choice = tk.StringVar(value="mp4", master=container_root)
    def set_choice(val):
        container_choice.set(val)
        container_root.quit()
    container_win = tk.Toplevel(container_root)
    container_win.title(title)
    container_win.geometry("300x150")
    container_win.attributes('-topmost', True)
    container_win.configure(bg="#23272e")
    apply_modern_theme(container_win)
    frame = create_styled_frame(container_win)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    create_styled_label(frame, prompt).pack(pady=10)
    create_styled_button(frame, "MP4", lambda: set_choice("mp4"), width=15).pack(pady=5)
    create_styled_button(frame, "MKV", lambda: set_choice("mkv"), width=15).pack(pady=5)
    container_win.protocol("WM_DELETE_WINDOW", container_root.quit)
    container_root.mainloop()
    ext = container_choice.get()
    container_root.destroy()
    return ext


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
    Settings dialog: speed (preset of the encoder), maximum height, audio, and what to do with HDR videos
    (when there is one). Only the heights below the tallest of the videos are offered.
    Returns a CompressionSettings, or None if the window is closed.
    """
    from tkinter import ttk
    infos = [video_info(path) for path in paths]
    heights = [height for height, _ in infos if height]
    tallest = max(heights, default=None)
    any_hdr = any(is_hdr for _, is_hdr in infos)
    root = tk.Tk()
    root.title("Compression settings")
    root.attributes('-topmost', True)
    root.configure(bg="#23272e")
    apply_modern_theme(root)
    frame = create_styled_frame(root)
    frame.pack(fill="both", expand=True, padx=14, pady=10)
    speed = tk.StringVar(master=root, value="balanced")
    max_height = tk.IntVar(master=root, value=0)  # 0: the resolution is kept
    audio_codec = tk.StringVar(master=root, value="aac")
    audio_kbps = tk.IntVar(master=root, value=AUDIO_BITRATE // 1000)
    keep_surround = tk.BooleanVar(master=root, value=False)
    hdr_to_sdr = tk.BooleanVar(master=root, value=False)
    note = {"font": ("Segoe UI", 9, "italic")}

    create_styled_label(frame, "Speed / quality", style='Title.TLabel').pack(anchor="w")
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
                                                 keep_surround.get(), audio_codec.get(), hdr_to_sdr.get())
        root.quit()
    create_styled_button(frame, "OK", ok, width=12).pack(pady=(12, 0))
    root.protocol("WM_DELETE_WINDOW", root.quit)
    root.mainloop()
    root.destroy()
    return result.get("settings")


def ask_max_size(title="Target Video Size", prompt="Enter the maximum file size in GB:"):
    """Asks for the target size in GB until it is valid; returns None if the dialog is cancelled."""
    while True:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        size_input = simpledialog.askstring(title, prompt, parent=root)
        root.destroy()
        if size_input is None:
            messagebox.showerror("❌ Error", "Unable to determine the max size.")
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
    Unified GUI workflow for compressing one or more video files with optional subtitle handling.
    """
    # Step 1: Select one or more video files
    file_paths = ask_video_files()
    if not file_paths:
        show_message("error", "File Error", "No video files selected. Please choose at least one video file.")
        return

    # If only one file, use single-file workflow
    if len(file_paths) == 1:
        path = file_paths[0]
        # Subtitles: sub_file is None when the video is compressed without subtitles
        sub_option, sub_file = ask_subtitles(path)

        ext = ask_container()
        if ext not in ("mp4", "mkv"):
            print(Fore.RED + "No container selected. Aborting." + Style.RESET_ALL)
            return
        encoder = choose_encoder()
        if encoder is None:
            print(Fore.RED + "No encoder selected. Aborting." + Style.RESET_ALL)
            return
        settings = ask_compression_settings(encoder, [path])
        if settings is None:
            print(Fore.RED + "No settings chosen. Aborting." + Style.RESET_ALL)
            return

        max_size_gb = ask_max_size()
        if max_size_gb is None:
            return

        try:
            run_compression(path, sub_option, sub_file, ext, max_size_gb, encoder=encoder, settings=settings)
        except CompressionError as e:
            print(Fore.RED + f"❌ {e}" + Style.RESET_ALL)
            show_message("error", "Compression failed", f"{os.path.basename(path)}:\n{e}")
        return

    # MULTIPLE FILES WORKFLOW (improved subtitle selection)
    # Step 2: Ask which videos need subtitles (checkbox list)
    from typing import List, Optional, Tuple
    subtitle_choices: List[Optional[Tuple[str, Optional[str]]]] = [None] * len(file_paths)
    checklist_root = tk.Tk()
    checklist_root.title("Select Videos for Subtitles")
    checklist_root.geometry("500x400")
    checklist_root.attributes('-topmost', True)
    checklist_root.configure(bg="#23272e")
    apply_modern_theme(checklist_root)
    need_subs = [tk.BooleanVar(master=checklist_root, value=False) for _ in file_paths]
    create_styled_label(checklist_root, "Select which videos need subtitles:", style='TLabel').pack(pady=10)
    frame = create_styled_frame(checklist_root)
    frame.pack(fill="both", expand=True)
    for i, path in enumerate(file_paths):
        ttk.Checkbutton(frame, text=os.path.basename(path), variable=need_subs[i], style='TCheckbutton').pack(fill="x", padx=30, pady=2)
    def ok():
        checklist_root.quit()
    create_styled_button(checklist_root, "OK", ok).pack(pady=12)
    checklist_root.mainloop()
    checklist_root.destroy()

    # Step 3: For checked videos, prompt for subtitle options; unchecked = none
    for i, path in enumerate(file_paths):
        subtitle_choices[i] = ask_subtitles(path) if need_subs[i].get() else ("none", None)

    # Step 3: Output container (reuse logic)
    ext = ask_container("Choose Output Container (Multiple)", "Choose the output container (applies to all):")
    if ext not in ("mp4", "mkv"):
        print(Fore.RED + "No container selected. Aborting." + Style.RESET_ALL)
        return
    encoder = choose_encoder()
    if encoder is None:
        print(Fore.RED + "No encoder selected. Aborting." + Style.RESET_ALL)
        return
    settings = ask_compression_settings(encoder, file_paths)
    if settings is None:
        print(Fore.RED + "No settings chosen. Aborting." + Style.RESET_ALL)
        return

    # Step 4: Max size (reuse logic)
    max_size_gb = ask_max_size("Target Video Size (Multiple)", "Enter the maximum file size in GB (applies to all):")
    if max_size_gb is None:
        return

    import threading
    import queue

    # GUI window for batch progress with scrollbar
    progress_root = tk.Tk()
    progress_root.title("Multiple Videos Compression Progress")
    w, h = 540, 420
    x = (progress_root.winfo_screenwidth() // 2) - (w // 2)
    y = (progress_root.winfo_screenheight() // 2) - (h // 2)
    progress_root.geometry(f"{w}x{h}+{x}+{y}")
    progress_root.attributes('-topmost', True)
    progress_root.configure(bg="#23272e")
    apply_modern_theme(progress_root)
    create_styled_label(progress_root, "Multiple Videos Compression Progress", style='Title.TLabel').pack(pady=(14, 8))

    # Scrollable frame setup
    canvas = tk.Canvas(progress_root, bg="#23272e", highlightthickness=0, width=w-20, height=h-80)
    scrollbar = ttk.Scrollbar(progress_root, orient="vertical", command=canvas.yview)
    scroll_frame = create_styled_frame(canvas)
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True, padx=(10,0), pady=(0,10))
    scrollbar.pack(side="right", fill="y", pady=(0,10))

    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    scroll_frame.bind("<Configure>", on_frame_configure)

    bars = []
    labels = []
    eta_labels = []
    for i, path in enumerate(file_paths):
        label = create_styled_label(scroll_frame, os.path.basename(path))
        label.pack(pady=(8, 0), anchor="w")
        bar = ttk.Progressbar(scroll_frame, length=400, mode='determinate', maximum=100, style='TProgressbar')
        bar.pack(pady=(2, 0), anchor="w")
        eta_label = create_styled_label(scroll_frame, "Time left: --:--", font=("Segoe UI", 10, "italic"))
        eta_label.pack(pady=(0, 2), anchor="w")
        bars.append(bar)
        labels.append(label)
        eta_labels.append(eta_label)
    progress_root.update()

    # Thread-safe queue for progress updates
    progress_queues = [queue.Queue() for _ in file_paths]
    failures = {}  # index of the video -> reason, filled by the worker threads, shown at the end

    def compress_one(idx, path, sub_option, sub_file):
        def gui_progress(percent, mins, secs):
            progress_queues[idx].put((percent, mins, secs))
        try:
            run_compression(path, sub_option, sub_file, ext, max_size_gb, gui_progress=gui_progress, encoder=encoder,
                            settings=settings)
        except CompressionError as e:
            print(Fore.RED + f"❌ {os.path.basename(path)}: {e}" + Style.RESET_ALL)
            failures[idx] = str(e)
        # Ensure bar is set to 100% at the end
        progress_queues[idx].put((100, 0, 0))

    threads = []
    for idx, (path, (sub_option, sub_file)) in enumerate(zip(file_paths, subtitle_choices)):
        t = threading.Thread(target=compress_one, args=(idx, path, sub_option, sub_file))
        t.start()
        threads.append(t)

    def update_bars():
        for i, q in enumerate(progress_queues):
            try:
                while True:
                    percent, mins, secs = q.get_nowait()
                    bars[i]['value'] = percent
                    if mins is not None and secs is not None:
                        eta_labels[i]['text'] = f"Time left: {mins:02d}:{secs:02d}"
                    else:
                        eta_labels[i]['text'] = "Time left: --:--"
                    progress_root.update_idletasks()
            except queue.Empty:
                pass
        if any(t.is_alive() for t in threads):
            progress_root.after(200, update_bars)
        else:
            # Finalize all bars to 100% and ETA to 00:00
            for i, (bar, eta) in enumerate(zip(bars, eta_labels)):
                bar['value'] = 100
                eta['text'] = "❌ Failed" if i in failures else "Time left: 00:00"
            progress_root.update_idletasks()
            done = len(file_paths) - len(failures)
            create_styled_label(progress_root, f"Multiple videos compression complete: {done}/{len(file_paths)} compressed.",
                                style='TLabel', foreground="green" if not failures else "orange").pack(pady=10)
            if failures:
                show_message("error", "Compression failed", "\n\n".join(
                    f"{os.path.basename(file_paths[i])}:\n{failures[i]}" for i in sorted(failures)))
            progress_root.after(2000, progress_root.destroy)

    update_bars()
    progress_root.mainloop()

    print(Fore.GREEN + f"\nMultiple videos compression complete: {len(file_paths) - len(failures)}/{len(file_paths)} "
          "files compressed." + Style.RESET_ALL)
