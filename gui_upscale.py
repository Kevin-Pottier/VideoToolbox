import tkinter as tk
from tkinter import filedialog, messagebox
import os
import cv2
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button

def get_video_resolution(filepath):
    try:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            return None, None
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return width, height
    except Exception as e:
        print(f"Error reading resolution: {e}")
        return None, None

def upscale_resolution_choices(width, height):
    # Returns a list of tuples (label, (w, h)) for higher available resolutions
    choices = []
    resolutions = [
        ("720p (1280x720)", (1280, 720)),
        ("1080p (1920x1080)", (1920, 1080)),
        ("4K (3840x2160)", (3840, 2160)),
    ]
    for label, (w, h) in resolutions:
        if h > height:
            choices.append((label, (w, h)))
    return choices

def run_video_upscale_gui():
    # Video selection
    root = tk.Tk()
    root.withdraw()
    filepaths = filedialog.askopenfilenames(
        title="Select one or more videos to upscale",
        filetypes=[("Video files", "*.mp4;*.mkv;*.avi;*.mov;*.webm")]
    )
    if not filepaths:
        print("No video selected.")
        return
    # For each video, detect resolution and ask for target
    upscale_jobs = []
    for filepath in filepaths:
        filename = os.path.basename(filepath)
        width, height = get_video_resolution(filepath)
        if width is None or height is None:
            messagebox.showerror("Error", f"Could not read resolution for {filename}.")
            continue
        choices = upscale_resolution_choices(width, height)
        if not choices:
            messagebox.showinfo("Info", f"{filename} ({width}x{height}): no higher resolution available.")
            continue
        # Dialog to choose target resolution
        choice_root = tk.Tk()
        choice_root.title(f"Upscale - {filename}")
        choice_root.geometry("350x220")
        apply_modern_theme(choice_root)
        frame = create_styled_frame(choice_root)
        frame.pack(fill="both", expand=True)
        create_styled_label(frame, f"{filename}", style='Title.TLabel').pack(pady=(12, 2))
        create_styled_label(frame, f"Original resolution: {width}x{height}").pack(pady=(0, 10))
        var = tk.StringVar()
        for label, (w, h) in choices:
            b = create_styled_button(frame, label, lambda l=label: var.set(l), width=20)
            b.pack(pady=4)
        def cancel():
            var.set("")
            choice_root.quit()
        create_styled_button(frame, "Cancel", cancel, width=20).pack(pady=(12, 0))
        def on_select(*_):
            choice_root.quit()
        var.trace_add('write', on_select)
        choice_root.mainloop()
        label = var.get()
        choice_root.destroy()
        if not label:
            print(f"Upscale cancelled for {filename}.")
            continue
        # Associate target resolution
        for l, (w, h) in choices:
            if l == label:
                upscale_jobs.append((filepath, (w, h)))
                break
    if not upscale_jobs:
        print("No video to upscale.")
        return
    # Output folder selection
    outdir = filedialog.askdirectory(title="Choose output folder for upscaled videos")
    if not outdir:
        print("No output folder selected.")
        return
    # Recap display (print)
    print("--- Upscale jobs to perform ---")
    for filepath, (w, h) in upscale_jobs:
        print(f"{os.path.basename(filepath)} : {w}x{h} => output folder: {outdir}")
    messagebox.showinfo("Simulation", "Upscaling would be launched here (see console for details).")
