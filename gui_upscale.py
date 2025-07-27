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
    
    if ensure_realesrgan_weights():
        print("Real-ESRGAN model is ready.")
    else:
        messagebox.showerror("Error", "Real-ESRGAN model not found. Please download it to the 'weights' folder.")
        return
    
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

    # 2. Upscale frames
    print(f"[{video_name}] Upscaling frames with Real-ESRGAN...")
    orig_h = get_video_resolution(filepath)[1]
    outscale = int(h / orig_h) + 1 if orig_h else 2
    realesrgan_script = os.path.abspath(os.path.normpath(os.path.join("extern", "Real-ESRGAN", "inference_realesrgan.py")))
    up_cmd = [
        "python", realesrgan_script,
        "-n", "RealESRGAN_x4plus",
        "-i", frames_dir,
        "-o", frames_up_dir,
        "--outscale", str(outscale)
    ]
    # Count number of frames to upscale
    frame_files = [f for f in os.listdir(frames_dir) if f.endswith('.jpg')]
    frame_files.sort()
    n_frames = len(frame_files)
    if use_tqdm and n_frames:
        print(f"[{video_name}] Progress: Upscaling {n_frames} frames...")
        with tqdm(total=n_frames, desc="Upscaling", unit="frame") as pbar:
            proc = subprocess.Popen(up_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            while True:
                line = proc.stderr.readline()
                if not line:
                    break
                if "Processed" in line or "Saving" in line:
                    pbar.update(1)
            proc.wait()
            pbar.n = n_frames
            pbar.refresh()
        res = proc
    else:
        res = subprocess.run(up_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[{video_name}] Upscale failed!")
        print(f"Command: {' '.join(up_cmd)}")
        print(f"stdout: {res.stdout}")
        print(f"stderr: {res.stderr}")
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


def ensure_realesrgan_weights(weights_dir="extern/Real-ESRGAN/weights", model_name="RealESRGAN_x4plus.pth"):
    """
    Checks if the Real-ESRGAN model file is present in the weights directory.
    If not, downloads it using wget.
    Returns the path to the model file, or None if download failed.
    """
    if not os.path.isdir(weights_dir):
        os.makedirs(weights_dir, exist_ok=True)
    model_path = os.path.join(weights_dir, model_name)
    if os.path.isfile(model_path):
        return model_path
    # Download the model if not present using Python (avoids wget/TLS issues)
    url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
    print(f"Model {model_name} not found in {weights_dir}. Downloading with Python...")
    try:
        import urllib.request
        with urllib.request.urlopen(url) as response, open(model_path, 'wb') as out_file:
            out_file.write(response.read())
        if os.path.isfile(model_path):
            print("Model downloaded successfully.")
            return model_path
        else:
            print("Failed to download model: file not found after download.")
            return None
    except Exception as e:
        print(f"Error downloading model: {e}")
        return None
