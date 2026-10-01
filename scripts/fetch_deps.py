"""
Download the external tools used by VideoToolbox.

Real-ESRGAN (realesrgan-ncnn-vulkan) is not stored in the repository: this script
downloads the official release archive, checks its SHA-256 and extracts only the
files the application needs into the Tool/ folder. It also checks that FFmpeg is
installed.

Usage (from anywhere, only the Python standard library is needed):
    python scripts/fetch_deps.py               # install what is missing
    python scripts/fetch_deps.py --force       # download again
    python scripts/fetch_deps.py --all-models  # also extract the models the app does not use
"""

import argparse
import hashlib
import os
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL_DIR = os.path.join(REPO_DIR, "Tool")

RELEASE_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-{}.zip"
# sys.platform -> (archive suffix, SHA-256 of the archive, executable, other files to extract)
ARCHIVES = {
    "win32": ("windows", "abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d",
              "realesrgan-ncnn-vulkan.exe", ["vcomp140.dll"]),
    "linux": ("ubuntu", "e5aa6eb131234b87c0c51f82b89390f5e3e642b7b70f2b9bbe95b6a285a40c96",
              "realesrgan-ncnn-vulkan", []),
    "darwin": ("macos", "e0ad05580abfeb25f8d8fb55aaf7bedf552c375b5b4d9bd3c8d59764d2cc333a",
               "realesrgan-ncnn-vulkan", []),
}
# Models offered by gui_upscale.py: live action (x4), and the fast animation video model (x2, x3, x4)
MODELS = ["realesrgan-x4plus", "realesr-animevideov3-x2", "realesr-animevideov3-x3", "realesr-animevideov3-x4"]

FFMPEG_HINTS = {
    "win32": "winget install Gyan.FFmpeg   (or https://www.gyan.dev/ffmpeg/builds/, then add bin/ to the PATH)",
    "linux": "sudo apt install ffmpeg",
    "darwin": "brew install ffmpeg",
}


def platform_key():
    return "linux" if sys.platform.startswith("linux") else sys.platform


def download(url, dest):
    last_percent = [-1]

    def progress(blocks, block_size, total):
        if total <= 0:
            return
        percent = min(100, blocks * block_size * 100 // total)
        if percent != last_percent[0]:
            last_percent[0] = percent
            print(f"\r  {percent:3d}% of {total / 1e6:.0f} MB", end="", flush=True)
    urllib.request.urlretrieve(url, dest, reporthook=progress)
    print()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_realesrgan(force, all_models):
    key = platform_key()
    if key not in ARCHIVES:
        print(f"Real-ESRGAN: no prebuilt binary for platform '{sys.platform}'.")
        return False
    suffix, expected_sha, exe_name, extra_files = ARCHIVES[key]
    exe_path = os.path.join(TOOL_DIR, exe_name)
    wanted = [exe_name] + extra_files
    if not all_models:
        wanted += [f"models/{model}.{ext}" for model in MODELS for ext in ("bin", "param")]

    missing = [name for name in wanted if not os.path.isfile(os.path.join(TOOL_DIR, name))]
    if not missing and not force and not all_models:
        print(f"Real-ESRGAN: already installed in {TOOL_DIR}")
        return True

    url = RELEASE_URL.format(suffix)
    print(f"Real-ESRGAN: downloading {url}")
    tmp_dir = tempfile.mkdtemp()
    try:
        archive = os.path.join(tmp_dir, "realesrgan.zip")
        try:
            download(url, archive)
        except OSError as e:
            print(f"Download failed: {e}")
            return False
        actual_sha = sha256(archive)
        if actual_sha != expected_sha:
            print(f"Checksum mismatch (expected {expected_sha}, got {actual_sha}): archive rejected.")
            return False

        with zipfile.ZipFile(archive) as zf:
            members = [m for m in zf.namelist() if not m.endswith("/")]
            if all_models:
                members = [m for m in members if m in wanted or m.startswith("models/")]
            else:
                members = [m for m in members if m in wanted]
            for member in members:
                target = os.path.join(TOOL_DIR, *member.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"  extracted Tool/{member}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if key != "win32":
        # zip archives do not keep the executable bit
        os.chmod(exe_path, os.stat(exe_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if key == "linux":
            print("  note: the upscaler needs a Vulkan driver (e.g. sudo apt install libvulkan1 mesa-vulkan-drivers)")
    print("Real-ESRGAN: installed.")
    return True


def check_ffmpeg():
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if not missing:
        print("FFmpeg: found in PATH.")
        return True
    print(f"FFmpeg: {' and '.join(missing)} not found in PATH. Install it with:")
    print(f"  {FFMPEG_HINTS.get(platform_key(), 'https://ffmpeg.org/download.html')}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Download the external tools used by VideoToolbox.")
    parser.add_argument("--force", action="store_true", help="download Real-ESRGAN again even if it is installed")
    parser.add_argument("--all-models", action="store_true", help="extract every Real-ESRGAN model, not only the one used")
    args = parser.parse_args()

    ok = install_realesrgan(args.force, args.all_models)
    ok = check_ffmpeg() and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
