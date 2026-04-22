import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import os
import pysrt
import concurrent.futures
import subprocess
import re
import threading
import queue
# Import reusable GUI helpers for modern, DRY window/dialog creation
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button


def add_subtitles_to_video(video_path, sub_option, sub_file, gui_progress=None):
    """
    Add subtitles to a video file using FFmpeg.
    Args:
        video_path (str): Path to the video file.
        sub_option (str): 'soft' for softcode (attach), 'hard' for hardcode (burn in).
        sub_file (str): Path to the subtitle file.
        gui_progress (callable): Optional callback for progress updates (percent, mins, secs).
    """
    from utils import ffprobe
    
    video_dir = os.path.dirname(video_path)
    video_name = os.path.basename(video_path)
    video_ext = os.path.splitext(video_path)[1]
    
    # Determine output filename
    output_file = os.path.splitext(video_path)[0] + f"_with_subtitles{video_ext}"
    output_name = os.path.basename(output_file)
    
    # Get video duration for progress
    try:
        duration_str = ffprobe([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", video_path
        ])
        duration = float(duration_str)
    except Exception:
        duration = 0
    
    # Build FFmpeg command based on subtitle option
    if sub_option == "soft":
        # Softcode: attach subtitle file to video
        sub_filename = os.path.basename(sub_file)
        ffmpeg_cmd = [
            "ffmpeg", "-i", video_name,
            "-i", sub_filename,
            "-c:s", "mov_text" if video_ext.lower() == ".mp4" else "srt",
            "-map", "0:v", "-map", "0:a", "-map", "1:s",
            "-c:v", "copy",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_name, "-y"
        ]
    else:  # hard
        # Hardcode: burn subtitles into video
        sub_filename = os.path.basename(sub_file)
        # Escape backslashes for FFmpeg filter
        sub_filter = sub_filename.replace("\\", "/")
        ffmpeg_cmd = [
            "ffmpeg", "-i", video_name,
            "-vf", f"subtitles='{sub_filter}'",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            output_name, "-y"
        ]
    
    print(Fore.YELLOW + f"\nAdding subtitles ({sub_option}) to: {video_name}\n" + Style.RESET_ALL)
    print("\tCommand:", " ".join(ffmpeg_cmd))
    
    # Run FFmpeg and capture progress
    import time
    proc = subprocess.Popen(ffmpeg_cmd, cwd=video_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    start_time = time.time()
    last_time = 0
    
    while True:
        line = proc.stderr.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        
        if "time=" in line:
            match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
            if match:
                h, m, s = match.groups()
                cur_time = int(h) * 3600 + int(m) * 60 + float(s)
                last_time = cur_time
                
                if duration > 0:
                    percent = min(100, int(cur_time / duration * 100))
                    elapsed = time.time() - start_time
                    if cur_time > 0 and percent < 100:
                        est_total = elapsed / (cur_time / duration)
                        remaining = est_total - elapsed
                        mins, secs = divmod(int(remaining), 60)
                    else:
                        mins, secs = None, None
                    
                    if gui_progress:
                        gui_progress(percent, mins, secs)
                else:
                    percent = 0
                    mins, secs = None, None
    
    proc.wait()
    
    # Final progress update
    if gui_progress:
        gui_progress(100, 0, 0)
    
    if proc.returncode == 0:
        print(Fore.GREEN + f"\n✅ Subtitles added successfully. Output: {output_file}" + Style.RESET_ALL)
        return output_file
    else:
        print(Fore.RED + f"\n❌ Failed to add subtitles." + Style.RESET_ALL)
        return None


def run_add_subtitles_gui():
    from tkinter import ttk
    
    # Step 1: Select one or more video files
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_paths = filedialog.askopenfilenames(title="Choose video file(s)", filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv")])
    root.destroy()
    
    if not file_paths:
        msg_root = tk.Tk()
        msg_root.attributes('-topmost', True)
        msg_root.withdraw()
        messagebox.showerror("File Error", "No video files selected. Please choose at least one video file.", parent=msg_root)
        msg_root.destroy()
        return
    
    # Single file workflow
    if len(file_paths) == 1:
        path = file_paths[0]
        sub_option, sub_file = prompt_subtitle_options(path)
        
        if sub_option is None:
            return
        
        # Process single file with progress window
        process_single_file(path, sub_option, sub_file)
        return
    
    # Multiple files workflow
    # Step 2: Ask which videos need subtitles
    subtitle_choices = [None] * len(file_paths)
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
    
    def ok_checklist():
        checklist_root.quit()
    
    create_styled_button(checklist_root, "OK", ok_checklist).pack(pady=12)
    checklist_root.mainloop()
    checklist_root.destroy()
    
    # Step 3: For checked videos, prompt for subtitle options
    for i, path in enumerate(file_paths):
        if not need_subs[i].get():
            subtitle_choices[i] = ("none", None)
            continue
        
        sub_option, sub_file = prompt_subtitle_options(path)
        if sub_option is None:
            # User cancelled
            return
        subtitle_choices[i] = (sub_option, sub_file)
    
    # Step 4: Process all files with progress window
    process_multiple_files(file_paths, subtitle_choices)


def prompt_subtitle_options(path):
    """
    Show dialog to choose subtitle option and file for a single video.
    Returns:
        tuple: (sub_option, sub_file) or (None, None) if cancelled
    """
    from tkinter import ttk
    
    sub_option = None
    sub_file = None
    
    while sub_option is None or (sub_option in ("soft", "hard") and not sub_file):
        sub_root = tk.Tk()
        sub_root.attributes('-topmost', True)
        sub_option_var = tk.StringVar(value="none")
        sub_file_var = tk.StringVar(value="")
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
            msg_root = tk.Tk()
            msg_root.attributes('-topmost', True)
            msg_root.withdraw()
            messagebox.showerror("Subtitle Error", "You selected a subtitle option but did not choose a subtitle file. Please choose a subtitle file.", parent=msg_root)
            msg_root.destroy()
    
    return (sub_option, sub_file)


def process_single_file(path, sub_option, sub_file):
    """Process a single video file with progress window."""
    from tkinter import ttk
    
    if sub_option == "none":
        msg_root = tk.Tk()
        msg_root.attributes('-topmost', True)
        msg_root.withdraw()
        messagebox.showinfo("No Subtitles", "No subtitle option selected. Nothing to do.", parent=msg_root)
        msg_root.destroy()
        return
    
    # Progress window
    progress_root = tk.Tk()
    progress_root.title("Adding Subtitles")
    progress_root.geometry("420x180")
    progress_root.attributes('-topmost', True)
    progress_root.configure(bg="#23272e")
    apply_modern_theme(progress_root)
    
    frame = create_styled_frame(progress_root)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    create_styled_label(frame, f"Adding subtitles to:", style='Title.TLabel').pack(pady=(0, 5))
    create_styled_label(frame, os.path.basename(path), style='TLabel').pack(pady=(0, 10))
    
    progress_var = tk.DoubleVar(value=0)
    progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=100, length=350, style='TProgressbar')
    progress_bar.pack(pady=6)
    
    percent_label = create_styled_label(frame, "0%", style='TLabel')
    percent_label.pack()
    
    time_label = create_styled_label(frame, "Estimated time left: --:--", style='TLabel', font=("Segoe UI", 10, "italic"))
    time_label.pack()
    
    def gui_progress(percent, mins, secs):
        progress_var.set(percent)
        percent_label.config(text=f"{percent}%")
        if mins is not None and secs is not None:
            time_label.config(text=f"Estimated time left: {mins:02d}:{secs:02d}")
        progress_root.update_idletasks()
    
    def run_in_thread():
        result = add_subtitles_to_video(path, sub_option, sub_file, gui_progress=gui_progress)
        progress_root.after(0, lambda: progress_var.set(100))
        progress_root.after(0, lambda: percent_label.config(text="100%"))
        progress_root.after(0, lambda: time_label.config(text="Completed!"))
        progress_root.update_idletasks()
        
        def show_result():
            if result:
                messagebox.showinfo("Success", f"Subtitles added successfully!\n\nOutput: {os.path.basename(result)}")
            else:
                messagebox.showerror("Error", "Failed to add subtitles.")
            progress_root.destroy()
        
        progress_root.after(100, show_result)
    
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    progress_root.mainloop()


def process_multiple_files(file_paths, subtitle_choices):
    """Process multiple video files with batch progress window."""
    from tkinter import ttk
    
    if all(choice[0] == "none" for choice in subtitle_choices):
        msg_root = tk.Tk()
        msg_root.attributes('-topmost', True)
        msg_root.withdraw()
        messagebox.showinfo("No Subtitles", "No subtitle option selected for any video. Nothing to do.", parent=msg_root)
        msg_root.destroy()
        return
    
    # Batch progress window
    progress_root = tk.Tk()
    progress_root.title("Multiple Videos - Adding Subtitles")
    w, h = 540, 420
    x = (progress_root.winfo_screenwidth() // 2) - (w // 2)
    y = (progress_root.winfo_screenheight() // 2) - (h // 2)
    progress_root.geometry(f"{w}x{h}+{x}+{y}")
    progress_root.attributes('-topmost', True)
    progress_root.configure(bg="#23272e")
    apply_modern_theme(progress_root)
    
    create_styled_label(progress_root, "Multiple Videos - Adding Subtitles", style='Title.TLabel').pack(pady=(14, 8))
    
    # Scrollable frame
    canvas = tk.Canvas(progress_root, bg="#23272e", highlightthickness=0, width=w-20, height=h-80)
    scrollbar = ttk.Scrollbar(progress_root, orient="vertical", command=canvas.yview)
    scroll_frame = create_styled_frame(canvas)
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
    progress_queues = []
    
    for i, path in enumerate(file_paths):
        sub_option, sub_file = subtitle_choices[i]
        label_text = os.path.basename(path)
        if sub_option != "none":
            label_text += f" ({sub_option})"
        
        label = create_styled_label(scroll_frame, label_text)
        label.pack(pady=(8, 0), anchor="w")
        
        bar = ttk.Progressbar(scroll_frame, length=400, mode='determinate', maximum=100, style='TProgressbar')
        bar.pack(pady=(2, 0), anchor="w")
        
        eta_label = create_styled_label(scroll_frame, "Time left: --:--", font=("Segoe UI", 10, "italic"))
        eta_label.pack(pady=(0, 2), anchor="w")
        
        bars.append(bar)
        labels.append(label)
        eta_labels.append(eta_label)
        progress_queues.append(queue.Queue())
    
    progress_root.update()
    
    def process_one(idx, path, sub_option, sub_file):
        def gui_progress(percent, mins, secs):
            progress_queues[idx].put((percent, mins, secs))
        
        if sub_option == "none":
            progress_queues[idx].put((100, 0, 0))
            return
        
        add_subtitles_to_video(path, sub_option, sub_file, gui_progress=gui_progress)
        progress_queues[idx].put((100, 0, 0))
    
    threads = []
    for idx, (path, (sub_option, sub_file)) in enumerate(zip(file_paths, subtitle_choices)):
        t = threading.Thread(target=process_one, args=(idx, path, sub_option, sub_file))
        t.start()
        threads.append(t)
    
    def update_bars():
        for i, q in enumerate(progress_queues):
            try:
                while True:
                    percent, mins, secs = q.get_nowait()
                    bars[i].config(value=percent)
                    if mins is not None and secs is not None:
                        eta_labels[i].config(text=f"Time left: {mins:02d}:{secs:02d}")
            except queue.Empty:
                pass
        
        if any(t.is_alive() for t in threads):
            progress_root.after(200, update_bars)
        else:
            for bar, eta in zip(bars, eta_labels):
                bar.config(value=100)
                eta.config(text="Time left: 00:00")
            progress_root.update_idletasks()
            create_styled_label(progress_root, "All videos processed!", style='TLabel', foreground="green").pack(pady=10)
            progress_root.after(2000, progress_root.destroy)
    
    update_bars()
    progress_root.mainloop()
    
    print(Fore.GREEN + f"\nMultiple videos subtitle processing complete. {len(file_paths)} files processed." + Style.RESET_ALL)