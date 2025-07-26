
import tkinter as tk
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button

from tkinter import filedialog, messagebox
import os
import cv2

def choose_usage_dialog():
    """
    Display a GUI window for the user to choose the main usage mode of the script.
    Returns:
        str: 'video_compression', 'sub_translation', or 'video_upscale' depending on user choice.
    """
    from tkinter import ttk
    usage = None
    def set_usage(val):
        nonlocal usage
        usage = val
        root.quit()
    root = tk.Tk()
    root.title("VideoCompress - Main Menu")
    root.geometry("380x270")
    root.configure(bg="#23272e")
    root.attributes('-topmost', True)
    # Center the window
    root.update_idletasks()
    w = 380
    h = 270
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    apply_modern_theme(root)
    frame = create_styled_frame(root)
    frame.pack(fill="both", expand=True)
    create_styled_label(frame, "VideoCompress", style='Title.TLabel').pack(pady=(18, 2))
    create_styled_label(frame, "Choose how to use this script:").pack(pady=(0, 16))
    create_styled_button(frame, "Video Compression", lambda: set_usage("video_compression"), width=22).pack(pady=7)
    create_styled_button(frame, "Subtitle Translation", lambda: set_usage("sub_translation"), width=22).pack(pady=7)
    create_styled_button(frame, "Upscale video (Real-ESRGAN)", lambda: set_usage("video_upscale"), width=22).pack(pady=7)
    root.mainloop()
    root.destroy()
    return usage

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

def main():
    """
    Main entry point for the script. Runs the selected workflow based on user choice.
    """
    usage = choose_usage_dialog()
    if usage == "video_compression":
        from gui_film import run_video_compression
        run_video_compression()
    elif usage == "sub_translation":
        from gui_subtitle import run_subtitle_translation
        run_subtitle_translation()
    elif usage == "video_upscale":
        run_video_upscale_gui()

if __name__ == "__main__":
    main()