
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
    from tkinter import ttk
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
            sub_root.configure(bg="#23272e")
            style = ttk.Style(sub_root)
            style.theme_use('clam')
            style.configure('TLabel', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 11))
            style.configure('TRadiobutton', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 10))
            style.configure('TButton', font=("Segoe UI", 11), padding=6, background="#2d333b", foreground="#ffffff")
            style.map('TButton', background=[('active', '#00bfff')], foreground=[('active', '#23272e')])
            frame = ttk.Frame(sub_root)
            frame.pack(fill="both", expand=True, padx=10, pady=10)
            ttk.Label(frame, text=f"Subtitle options for:\n{os.path.basename(path)}").pack(pady=5)
            def toggle_sub():
                if sub_option_var.get() == "none":
                    sub_btn.state(["disabled"])
                    sub_file_var.set("")
                else:
                    sub_btn.state(["!disabled"])
            ttk.Radiobutton(frame, text="No subtitles", variable=sub_option_var, value="none", command=toggle_sub).pack(anchor="w", padx=40)
            ttk.Radiobutton(frame, text="Softcode (attach .srt)", variable=sub_option_var, value="soft", command=toggle_sub).pack(anchor="w", padx=40)
            ttk.Radiobutton(frame, text="Hardcode (burn in)", variable=sub_option_var, value="hard", command=toggle_sub).pack(anchor="w", padx=40)
            sub_btn = ttk.Button(frame, text="Choose Subtitle File", command=lambda: sub_file_var.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]) or sub_file_var.get()))
            sub_btn.pack(pady=5)
            sub_btn.state(["disabled"])
            sub_label = ttk.Label(frame, textvariable=sub_file_var)
            sub_label.pack(pady=5)
            def ok():
                sub_root.quit()
            ttk.Button(frame, text="OK", command=ok).pack(pady=10)
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
        container_win.configure(bg="#23272e")
        style = ttk.Style(container_win)
        style.theme_use('clam')
        style.configure('TLabel', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 11))
        style.configure('TButton', font=("Segoe UI", 11), padding=6, background="#2d333b", foreground="#ffffff")
        style.map('TButton', background=[('active', '#00bfff')], foreground=[('active', '#23272e')])
        frame = ttk.Frame(container_win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(frame, text="Choose the output container:").pack(pady=10)
        ttk.Button(frame, text="MP4", width=15, command=lambda: set_choice("mp4")).pack(pady=5)
        ttk.Button(frame, text="MKV", width=15, command=lambda: set_choice("mkv")).pack(pady=5)
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
            # Use ttk simpledialog if available, else fallback
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

    # MULTIPLE FILES WORKFLOW (improved subtitle selection)
    # Step 2: Ask which videos need subtitles (checkbox list)
    subtitle_choices = [None] * len(file_paths)
    checklist_root = tk.Tk()
    checklist_root.title("Select Videos for Subtitles")
    checklist_root.geometry("500x400")
    checklist_root.attributes('-topmost', True)
    checklist_root.configure(bg="#23272e")
    style = ttk.Style(checklist_root)
    style.theme_use('clam')
    style.configure('TLabel', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 12, "bold"))
    style.configure('TCheckbutton', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 10))
    style.configure('TButton', font=("Segoe UI", 11), padding=6, background="#2d333b", foreground="#ffffff")
    style.map('TButton', background=[('active', '#00bfff')], foreground=[('active', '#23272e')])
    need_subs = [tk.BooleanVar(master=checklist_root, value=False) for _ in file_paths]
    ttk.Label(checklist_root, text="Select which videos need subtitles:").pack(pady=10)
    frame = ttk.Frame(checklist_root)
    frame.pack(fill="both", expand=True)
    for i, path in enumerate(file_paths):
        ttk.Checkbutton(frame, text=os.path.basename(path), variable=need_subs[i], style='TCheckbutton').pack(fill="x", padx=30, pady=2)
    def ok():
        checklist_root.quit()
    ttk.Button(checklist_root, text="OK", command=ok).pack(pady=12)
    checklist_root.mainloop()
    checklist_root.destroy()

    # Step 3: For checked videos, prompt for subtitle options; unchecked = none
    for i, path in enumerate(file_paths):
        if not need_subs[i].get():
            subtitle_choices[i] = ("none", None)
            continue
        sub_option = None
        sub_file = None
        while sub_option is None or (sub_option in ("soft", "hard") and not sub_file):
            sub_root = tk.Tk()
            sub_root.attributes('-topmost', True)
            sub_option_var = tk.StringVar(value="none")
            sub_file_var = tk.StringVar(value="")
            sub_root.title(f"Subtitle Options for {os.path.basename(path)}")
            sub_root.geometry("400x240")
            sub_root.configure(bg="#23272e")
            style = ttk.Style(sub_root)
            style.theme_use('clam')
            style.configure('TLabel', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 11))
            style.configure('TRadiobutton', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 10))
            style.configure('TButton', font=("Segoe UI", 11), padding=6, background="#2d333b", foreground="#ffffff")
            style.map('TButton', background=[('active', '#00bfff')], foreground=[('active', '#23272e')])
            frame = ttk.Frame(sub_root)
            frame.pack(fill="both", expand=True, padx=10, pady=10)
            ttk.Label(frame, text=f"Subtitle options for:\n{os.path.basename(path)}").pack(pady=5)
            def toggle_sub():
                if sub_option_var.get() == "none":
                    sub_btn.state(["disabled"])
                    sub_file_var.set("")
                else:
                    sub_btn.state(["!disabled"])
            ttk.Radiobutton(frame, text="No subtitles", variable=sub_option_var, value="none", command=toggle_sub).pack(anchor="w", padx=40)
            ttk.Radiobutton(frame, text="Softcode (attach .srt)", variable=sub_option_var, value="soft", command=toggle_sub).pack(anchor="w", padx=40)
            ttk.Radiobutton(frame, text="Hardcode (burn in)", variable=sub_option_var, value="hard", command=toggle_sub).pack(anchor="w", padx=40)
            sub_btn = ttk.Button(frame, text="Choose Subtitle File", command=lambda: sub_file_var.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]) or sub_file_var.get()))
            sub_btn.pack(pady=5)
            sub_btn.state(["disabled"])
            sub_label = ttk.Label(frame, textvariable=sub_file_var)
            sub_label.pack(pady=5)
            def ok():
                sub_root.quit()
            ttk.Button(frame, text="OK", command=ok).pack(pady=10)
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
        subtitle_choices[i] = (sub_option, sub_file)

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
    container_win.configure(bg="#23272e")
    style = ttk.Style(container_win)
    style.theme_use('clam')
    style.configure('TLabel', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 11))
    style.configure('TButton', font=("Segoe UI", 11), padding=6, background="#2d333b", foreground="#ffffff")
    style.map('TButton', background=[('active', '#00bfff')], foreground=[('active', '#23272e')])
    frame = ttk.Frame(container_win)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    ttk.Label(frame, text="Choose the output container (applies to all):").pack(pady=10)
    ttk.Button(frame, text="MP4", width=15, command=lambda: set_choice("mp4")).pack(pady=5)
    ttk.Button(frame, text="MKV", width=15, command=lambda: set_choice("mkv")).pack(pady=5)
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

    # GUI window for batch progress with scrollbar
    progress_root = tk.Tk()
    progress_root.title("Multiple Videos Compression Progress")
    w, h = 540, 420
    x = (progress_root.winfo_screenwidth() // 2) - (w // 2)
    y = (progress_root.winfo_screenheight() // 2) - (h // 2)
    progress_root.geometry(f"{w}x{h}+{x}+{y}")
    progress_root.attributes('-topmost', True)
    progress_root.configure(bg="#23272e")
    style = ttk.Style(progress_root)
    style.theme_use('clam')
    style.configure('TLabel', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 11))
    style.configure('Title.TLabel', background="#23272e", foreground="#00bfff", font=("Segoe UI", 14, "bold"))
    style.configure('TButton', font=("Segoe UI", 11), padding=6, background="#2d333b", foreground="#ffffff")
    style.map('TButton', background=[('active', '#00bfff')], foreground=[('active', '#23272e')])
    style.configure('TProgressbar', troughcolor="#23272e", background="#00bfff", thickness=18)
    ttk.Label(progress_root, text="Multiple Videos Compression Progress", style='Title.TLabel').pack(pady=(14, 8))

    # Scrollable frame setup
    canvas = tk.Canvas(progress_root, bg="#23272e", highlightthickness=0, width=w-20, height=h-80)
    scrollbar = ttk.Scrollbar(progress_root, orient="vertical", command=canvas.yview)
    scroll_frame = ttk.Frame(canvas, style='TFrame')
    scroll_frame_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
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
        label = ttk.Label(scroll_frame, text=os.path.basename(path), style='TLabel')
        label.pack(pady=(8, 0), anchor="w")
        bar = ttk.Progressbar(scroll_frame, length=400, mode='determinate', maximum=100, style='TProgressbar')
        bar.pack(pady=(2, 0), anchor="w")
        eta_label = ttk.Label(scroll_frame, text="Time left: --:--", style='TLabel', font=("Segoe UI", 10, "italic"))
        eta_label.pack(pady=(0, 2), anchor="w")
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
            ttk.Label(progress_root, text="Multiple videos compression complete.", foreground="green").pack(pady=10)
            progress_root.after(2000, progress_root.destroy)

    update_bars()
    progress_root.mainloop()

    print(Fore.GREEN + f"\nMultiple videos compression complete. {len(file_paths)} files processed." + Style.RESET_ALL)
