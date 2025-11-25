import subprocess
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
        run_upscale(filepath, w, h, outdir)
    messagebox.showinfo("Done", "Upscaling process finished. See console for details.")


def run_upscale(filepath, w, h, outdir):
    """
    Run the full upscale process for a single video: extract frames, upscale, recompose.
    """
    video_name = os.path.splitext(os.path.basename(filepath))[0]
    frames_dir = os.path.abspath(os.path.normpath(os.path.join(outdir, f"frames_{video_name}")))
    frames_up_dir = os.path.abspath(os.path.normpath(os.path.join(outdir, f"frames_upscaled_{video_name}")))
    output_video = os.path.abspath(os.path.normpath(os.path.join(outdir, f"{video_name}_upscaled_{h}p.mp4")))
    filepath = os.path.abspath(os.path.normpath(filepath))
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(frames_up_dir, exist_ok=True)

    # 1. Extract frames
    print(f"[{video_name}] Extracting frames...")
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False

    # Estimate number of frames using ffprobe
    try:
        import subprocess as sp
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=nb_read_frames", "-of", "default=nokey=1:noprint_wrappers=1", filepath
        ]
        nb_frames = int(sp.check_output(probe_cmd, stderr=sp.DEVNULL).decode().strip())
    except Exception:
        nb_frames = None

    extract_cmd = [
        "ffmpeg", "-i", filepath, "-qscale:v", "1",
        os.path.join(frames_dir, "frame_%08d.jpg")
    ]
    if use_tqdm and nb_frames:
        print(f"[{video_name}] Progress: Extracting {nb_frames} frames...")
        with tqdm(total=nb_frames, desc="Extracting", unit="frame") as pbar:
            proc = subprocess.Popen(extract_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            while True:
                line = proc.stderr.readline()
                if not line:
                    break
                if "frame=" in line:
                    try:
                        current = int(line.split("frame=")[-1].split()[0])
                        pbar.n = current
                        pbar.refresh()
                    except Exception:
                        pass
            proc.wait()
            pbar.n = nb_frames
            pbar.refresh()
        res = proc
    else:
        res = subprocess.run(extract_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        err = res.stderr.read() if hasattr(res.stderr, 'read') else res.stderr
        print(f"[{video_name}] Frame extraction failed: {err}")
        return False

    # 2. Upscale frames using realesrgan-ncnn-vulkan.exe in batch mode with GUI progress bar
    print(f"[{video_name}] Upscaling frames with realesrgan-ncnn-vulkan.exe (batch mode)...")
    tool_dir = os.path.abspath(os.path.normpath(os.path.join(os.getcwd(), "Tool")))
    exe_path = os.path.join(tool_dir, "realesrgan-ncnn-vulkan.exe")
    if not os.path.isfile(exe_path):
        print(f"[{video_name}] ERROR: realesrgan-ncnn-vulkan.exe not found in {tool_dir}")
        return False
    model_name = "realesrgan-x4plus"  # or change to another model if needed
    # Calculate scale factor based on chosen resolution
    orig_width, orig_height = get_video_resolution(filepath)
    if orig_height is None or orig_height == 0:
        scale = 2  # fallback
    else:
        scale = int(h / orig_height) + 1
        if scale < 2:
            scale = 2  # minimum supported by realesrgan
    up_cmd = [
        exe_path,
        "-i", frames_dir,
        "-o", frames_up_dir,
        "-n", model_name,
        "-s", str(scale),
        "-f", "jpg"
    ]
    print(f"[{video_name}] Upscale command: {' '.join(up_cmd)}")
    # Count input frames
    frame_files = [f for f in os.listdir(frames_dir) if f.endswith('.jpg')]
    n_frames = len(frame_files)
    # --- GUI progress bar ---
    import threading, time
    import tkinter as tk
    from tkinter import ttk
    progress_root = tk.Toplevel()
    progress_root.title(f"Upscaling {video_name}")
    progress_root.geometry("420x120")
    progress_label = tk.Label(progress_root, text=f"Upscaling {n_frames} frames...", font=("Segoe UI", 12))
    progress_label.pack(pady=(18, 4))
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(progress_root, maximum=n_frames, length=360, variable=progress_var)
    progress_bar.pack(pady=6)
    eta_label = tk.Label(progress_root, text="ETA: --:--", font=("Segoe UI", 10))
    eta_label.pack(pady=(0, 8))
    progress_root.update()
    # Thread to run upscaling
    def upscale_thread():
        start_time = time.time()
        proc = subprocess.Popen(up_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        while True:
            # Count output files
            out_files = [f for f in os.listdir(frames_up_dir) if f.endswith('.jpg')]
            done = len(out_files)
            progress_var.set(done)
            elapsed = time.time() - start_time
            if done > 0:
                rate = elapsed / done
                eta = int(rate * (n_frames - done))
                eta_str = time.strftime('%M:%S', time.gmtime(eta))
            else:
                eta_str = "--:--"
            eta_label.config(text=f"ETA: {eta_str}")
            progress_root.update()
            if proc.poll() is not None:
                # One last update
                out_files = [f for f in os.listdir(frames_up_dir) if f.endswith('.jpg')]
                done = len(out_files)
                progress_var.set(done)
                progress_root.update()
                break
            time.sleep(0.5)
        # Check result
        if proc.returncode != 0:
            print(f"[{video_name}] Upscale failed!")
            print(f"Command: {' '.join(up_cmd)}")
            out, err = proc.communicate()
            print(f"stdout: {out}")
            print(f"stderr: {err}")
            progress_queue.put({"finished": True, "success": False})
            return
        progress_queue.put({"finished": True, "success": True})

    # Function to process queue and update GUI
    def process_queue():
        try:
            while True:
                msg = progress_queue.get_nowait()
                if "done" in msg:
                    progress_var.set(msg["done"])
                if "eta_str" in msg:
                    eta_label.config(text=f"ETA: {msg['eta_str']}")
                if msg.get("finished"):
                    # If success is set, store it
                    if "success" in msg:
                        upscale_result["success"] = msg["success"]
                    progress_root.after(100, progress_root.destroy)
                    return
        except queue.Empty:
            pass
        progress_root.after(100, process_queue)

    t = threading.Thread(target=upscale_thread)
    t.start()
    process_queue()
    progress_root.mainloop()
    t.join()
    if upscale_result["success"] is False:
        return False
    # 3. Recompose video
    print(f"[{video_name}] Recomposing video...")
    upscaled_files = [f for f in os.listdir(frames_up_dir) if f.endswith('_out.jpg')]
    upscaled_files.sort()
    n_upscaled = len(upscaled_files)
    recompose_cmd = [
        "ffmpeg",
        "-i", os.path.join(frames_up_dir, "frame_%08d_out.jpg"),
        "-i", filepath,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-crf", "18", "-preset", "slow",
        "-c:a", "copy",
        output_video
    ]
    if use_tqdm and n_upscaled:
        print(f"[{video_name}] Progress: Recomposing {n_upscaled} frames...")
        print(f"[{video_name}] command used for recomposition: {' '.join(recompose_cmd)}")
        with tqdm(total=n_upscaled, desc="Recomposing", unit="frame") as pbar:
            proc = subprocess.Popen(recompose_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            while True:
                line = proc.stderr.readline()
                if not line:
                    break
                if "frame=" in line:
                    try:
                        current = int(line.split("frame=")[-1].split()[0])
                        pbar.n = current
                        pbar.refresh()
                    except Exception:
                        pass
            proc.wait()
            pbar.n = n_upscaled
            pbar.refresh()
        res = proc
    else:
        res = subprocess.run(recompose_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        err = res.stderr.read() if hasattr(res.stderr, 'read') else res.stderr
        print(f"[{video_name}] Recomposition failed: {err}")
        return False
    print(f"[{video_name}] Upscaled video saved to {output_video}")
    return True

