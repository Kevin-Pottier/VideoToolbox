
import concurrent.futures
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from colorama import Fore, Style
import os
from compression import run_compression

def run_video_compression():
    """
    Unified GUI workflow for compressing one or more video files with optional subtitle handling.
    """
    # Step 1: Select one or more video files
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_paths = filedialog.askopenfilenames(title="Choose video file(s)", filetypes=[("Videos", "*.mp4 *.mkv *.avi")])
    root.destroy()
    if not file_paths:
        msg_root = tk.Tk()
        msg_root.attributes('-topmost', True)
        msg_root.withdraw()
        messagebox.showerror("File Error", "No video files selected. Please choose at least one video file.", parent=msg_root)
        msg_root.destroy()
        return

    # If only one file, use single-file workflow
    if len(file_paths) == 1:
        path = file_paths[0]
        # Subtitle options
        sub_option = None
        sub_file = None
        while sub_option is None or (sub_option in ("soft", "hard") and not sub_file):
            sub_root = tk.Tk()
            sub_root.attributes('-topmost', True)
            sub_option_var = tk.StringVar(value="none")
            sub_file_var = tk.StringVar(value="")
            sub_root.title(f"Subtitle Options for {os.path.basename(path)}")
            sub_root.geometry("400x240")
            tk.Label(sub_root, text=f"Subtitle options for:\n{os.path.basename(path)}").pack(pady=5)
            def toggle_sub():
                if sub_option_var.get() == "none":
                    sub_btn.config(state="disabled")
                    sub_file_var.set("")
                else:
                    sub_btn.config(state="normal")
            tk.Radiobutton(sub_root, text="No subtitles", variable=sub_option_var, value="none", command=toggle_sub).pack(anchor="w", padx=40)
            tk.Radiobutton(sub_root, text="Softcode (attach .srt)", variable=sub_option_var, value="soft", command=toggle_sub).pack(anchor="w", padx=40)
            tk.Radiobutton(sub_root, text="Hardcode (burn in)", variable=sub_option_var, value="hard", command=toggle_sub).pack(anchor="w", padx=40)
            sub_btn = tk.Button(sub_root, text="Choose Subtitle File", state="disabled", command=lambda: sub_file_var.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]) or sub_file_var.get()))
            sub_btn.pack(pady=5)
            sub_label = tk.Label(sub_root, textvariable=sub_file_var)
            sub_label.pack(pady=5)
            def ok():
                sub_root.quit()
            tk.Button(sub_root, text="OK", command=ok).pack(pady=10)
            sub_root.after(100, toggle_sub)
            sub_root.mainloop()
            sub_option = sub_option_var.get()
            sub_file = sub_file_var.get() if sub_file_var.get() else None
            sub_root.destroy()
            if sub_option in ("soft", "hard") and not sub_file:
                msg_root = tk.Tk()
                msg_root.attributes('-topmost', True)
                msg_root.withdraw()
                messagebox.showerror("Subtitle Error", "You selected a subtitle option but did not choose a subtitle file. Please choose a subtitle file.", parent=msg_root)
                msg_root.destroy()

        # Output container
        container_root = tk.Tk()
        container_root.withdraw()
        container_root.attributes('-topmost', True)
        container_choice = tk.StringVar(value="mp4")
        def set_choice(val):
            container_choice.set(val)
            container_root.quit()
        container_win = tk.Toplevel(container_root)
        container_win.title("Choose Output Container")
        container_win.geometry("300x150")
        container_win.attributes('-topmost', True)
        tk.Label(container_win, text="Choose the output container:").pack(pady=10)
        tk.Button(container_win, text="MP4", width=15, command=lambda: set_choice("mp4")).pack(pady=5)
        tk.Button(container_win, text="MKV", width=15, command=lambda: set_choice("mkv")).pack(pady=5)
        container_win.protocol("WM_DELETE_WINDOW", container_root.quit)
        container_root.mainloop()
        ext = container_choice.get()
        container_root.destroy()
        if ext not in ("mp4", "mkv"):
            print(Fore.RED + "No container selected. Aborting." + Style.RESET_ALL)
            return

        # Max size
        max_size_gb = None
        while max_size_gb is None or max_size_gb <= 0:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            try:
                max_size_gb = float(simpledialog.askstring("Target Video Size", "Enter the maximum file size in GB:", parent=root))
            except Exception:
                max_size_gb = None
            root.destroy()
            if not max_size_gb or max_size_gb <= 0:
                msg_root = tk.Tk()
                msg_root.attributes('-topmost', True)
                msg_root.withdraw()
                messagebox.showerror("Size Error", "Invalid size. Must be greater than 0.", parent=msg_root)
                msg_root.destroy()

        run_compression(path, sub_option, sub_file, ext, max_size_gb)
        return

    # MULTIPLE FILES WORKFLOW (same as previous batch logic)
    # Step 2: Subtitle options PER VIDEO
    subtitle_choices = []  # List of (sub_option, sub_file) per video
    for path in file_paths:
        sub_option = None
        sub_file = None
        while sub_option is None or (sub_option in ("soft", "hard") and not sub_file):
            sub_root = tk.Tk()
            sub_root.attributes('-topmost', True)
            sub_option_var = tk.StringVar(value="none")
            sub_file_var = tk.StringVar(value="")
            sub_root.title(f"Subtitle Options for {os.path.basename(path)}")
            sub_root.geometry("400x240")
            tk.Label(sub_root, text=f"Subtitle options for:\n{os.path.basename(path)}").pack(pady=5)
            def toggle_sub():
                if sub_option_var.get() == "none":
                    sub_btn.config(state="disabled")
                    sub_file_var.set("")
                else:
                    sub_btn.config(state="normal")
            tk.Radiobutton(sub_root, text="No subtitles", variable=sub_option_var, value="none", command=toggle_sub).pack(anchor="w", padx=40)
            tk.Radiobutton(sub_root, text="Softcode (attach .srt)", variable=sub_option_var, value="soft", command=toggle_sub).pack(anchor="w", padx=40)
            tk.Radiobutton(sub_root, text="Hardcode (burn in)", variable=sub_option_var, value="hard", command=toggle_sub).pack(anchor="w", padx=40)
            sub_btn = tk.Button(sub_root, text="Choose Subtitle File", state="disabled", command=lambda: sub_file_var.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]) or sub_file_var.get()))
            sub_btn.pack(pady=5)
            sub_label = tk.Label(sub_root, textvariable=sub_file_var)
            sub_label.pack(pady=5)
            def ok():
                sub_root.quit()
            tk.Button(sub_root, text="OK", command=ok).pack(pady=10)
            sub_root.after(100, toggle_sub)
            sub_root.mainloop()
            sub_option = sub_option_var.get()
            sub_file = sub_file_var.get() if sub_file_var.get() else None
            sub_root.destroy()
            if sub_option in ("soft", "hard") and not sub_file:
                msg_root = tk.Tk()
                msg_root.attributes('-topmost', True)
                msg_root.withdraw()
                messagebox.showerror("Subtitle Error", "You selected a subtitle option but did not choose a subtitle file. Please choose a subtitle file.", parent=msg_root)
                msg_root.destroy()
        subtitle_choices.append((sub_option, sub_file))

    # Step 3: Output container (reuse logic)
    container_root = tk.Tk()
    container_root.withdraw()
    container_root.attributes('-topmost', True)
    container_choice = tk.StringVar(value="mp4")
    def set_choice(val):
        container_choice.set(val)
        container_root.quit()
    container_win = tk.Toplevel(container_root)
    container_win.title("Choose Output Container (Multiple)")
    container_win.geometry("300x150")
    container_win.attributes('-topmost', True)
    tk.Label(container_win, text="Choose the output container (applies to all):").pack(pady=10)
    tk.Button(container_win, text="MP4", width=15, command=lambda: set_choice("mp4")).pack(pady=5)
    tk.Button(container_win, text="MKV", width=15, command=lambda: set_choice("mkv")).pack(pady=5)
    container_win.protocol("WM_DELETE_WINDOW", container_root.quit)
    container_root.mainloop()
    ext = container_choice.get()
    container_root.destroy()
    if ext not in ("mp4", "mkv"):
        print(Fore.RED + "No container selected. Aborting." + Style.RESET_ALL)
        return

    # Step 4: Max size (reuse logic)
    max_size_gb = None
    while max_size_gb is None or max_size_gb <= 0:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            max_size_gb = float(simpledialog.askstring("Target Video Size (Multiple)", "Enter the maximum file size in GB (applies to all):", parent=root))
        except Exception:
            max_size_gb = None
        root.destroy()
        if not max_size_gb or max_size_gb <= 0:
            msg_root = tk.Tk()
            msg_root.attributes('-topmost', True)
            msg_root.withdraw()
            messagebox.showerror("Size Error", "Invalid size. Must be greater than 0.", parent=msg_root)
            msg_root.destroy()

    import threading
    import queue
    from tkinter import ttk

    # GUI window for batch progress
    progress_root = tk.Tk()
    progress_root.title("Multiple Videos Compression Progress")
    progress_root.geometry(f"500x{100+40*len(file_paths)}")
    progress_root.attributes('-topmost', True)
    tk.Label(progress_root, text="Multiple Videos Compression Progress").pack(pady=10)
    bars = []
    labels = []
    eta_labels = []
    for i, path in enumerate(file_paths):
        label = tk.Label(progress_root, text=os.path.basename(path))
        label.pack()
        bar = ttk.Progressbar(progress_root, length=400, mode='determinate', maximum=100)
        bar.pack(pady=2)
        eta_label = tk.Label(progress_root, text="Time left: --:--")
        eta_label.pack()
        bars.append(bar)
        labels.append(label)
        eta_labels.append(eta_label)
    progress_root.update()

    # Thread-safe queue for progress updates
    progress_queues = [queue.Queue() for _ in file_paths]

    def compress_one(idx, path, sub_option, sub_file):
        def gui_progress(percent, mins, secs):
            progress_queues[idx].put((percent, mins, secs))
        run_compression(path, sub_option, sub_file, ext, max_size_gb, gui_progress=gui_progress)
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
            for bar, eta in zip(bars, eta_labels):
                bar['value'] = 100
                eta['text'] = "Time left: 00:00"
            progress_root.update_idletasks()
            tk.Label(progress_root, text="Multiple videos compression complete.", fg="green").pack(pady=10)
            progress_root.after(2000, progress_root.destroy)

    update_bars()
    progress_root.mainloop()

    print(Fore.GREEN + f"\nMultiple videos compression complete. {len(file_paths)} files processed." + Style.RESET_ALL)
