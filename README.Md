

# VideoCompress

[![CI](https://github.com/Kevin-Pottier/VideoToolbox/actions/workflows/ci.yml/badge.svg)](https://github.com/Kevin-Pottier/VideoToolbox/actions/workflows/ci.yml)

Modern, user-friendly Python GUI for compressing or upscaling one or multiple video files and translating subtitles, with per-file progress, ETA, advanced batch features, and a fast, responsive, multi-threaded subtitle translation workflow with GUI progress bar. Now includes Real-ESRGAN integration for high-quality video upscaling.

## Features
- Unified video compression and upscaling: select one or multiple videos, all in one workflow.
- **Real-ESRGAN upscaling**: upscale videos to higher resolutions using state-of-the-art AI (Real-ESRGAN). Choose the target resolution (720p, 1080p, 4K).
- Batch mode: see all progress bars in a scrollable window, with per-file ETA.
- Modern UI: clean, dark-themed interface, clear fonts, colors, and spacing.
- Subtitle handling: for each video, choose to ignore, softcode, or hardcode subtitles.
- Efficient batch subtitle workflow: first select which videos need subtitles, then only configure those.
- Subtitle translation: translate .srt files between languages with a fast, multi-threaded workflow, real-time GUI progress bar, and completion notification.
- Robust error handling and user feedback throughout.

## Requirements

- Python 3.9 or newer
- FFmpeg and FFprobe installed and available in your system PATH
- Python packages listed in `requirements.txt`:
  - `colorama` (for colored terminal output)
  - `pysrt` (for reading/writing subtitle files)
  - `deep-translator` (for Google Translate API)
  - `tkinter` (standard library)
- For upscaling: the portable [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) tool `realesrgan-ncnn-vulkan` (no Python/CUDA/PyTorch needed, it uses your GPU through Vulkan). It is **not stored in the repository**: `scripts/fetch_deps.py` downloads the official release (Windows, Linux or macOS) into the `Tool/` folder.

## Usage

0. Clone the repo using: 
   ```bash
   git clone https://github.com/Kevin-Pottier/VideoToolbox.git
   ```
1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Download the external tools and check that FFmpeg is installed (the official Real-ESRGAN archive, ~75 MB, is SHA-256 checked and only the files the app uses, ~40 MB, are kept):
   ```bash
   python scripts/fetch_deps.py
   ```
   If FFmpeg is missing, the script tells you how to install it (e.g. `winget install Gyan.FFmpeg` on Windows).
3. Run the app:
   ```bash
   python main.py
   ```
4. Choose a mode:
   - **Video Compression**: Select one or more videos, configure subtitles, output format, and size. The video is encoded in two passes (an analysis pass, then the real encode) so that the file ends up just under the requested size. Batch mode shows a scrollable window with per-file progress and ETA.
   - **Video Upscaling (Real-ESRGAN)**: Select one or more videos to upscale and choose the target resolution (720p, 1080p, 4K). Frames are upscaled x4 by Real-ESRGAN then resized to the target height, keeping the aspect ratio, frame rate and audio. A progress window shows each step with its ETA (closing it cancels). Output is saved in the selected folder. ⚠️ The temporary frames need a lot of disk space (hundreds of GB for a full movie): the app estimates it before starting.
   - **Subtitle Translation**: Translate one or more `.srt` files (UTF-8 or Windows-1252) between languages. The translation is fast (multi-threaded), the GUI remains responsive, and a progress bar shows real-time status. When finished, a message box confirms completion (and reports the lines that could not be translated) and the window closes automatically.
   - **Audio fix for stereo**: Down-mix every audio track to stereo AAC. All tracks, subtitles and attachments are kept; French audio tracks are moved first and the first one becomes the default track (detected from the language tag, or from titles such as `VFF`/`VFQ`).
   - **Add subtitles**: Add a subtitle file (`.srt`/`.ass`, from any folder, any encoding) as a new track, keeping the existing ones, or burn it into the video.
   - **Audio Tracks Management**: Choose which audio tracks to keep and the default one. For MP4 output, text subtitles are converted to `mov_text` and image subtitles (PGS, DVD) are skipped: choose MKV to keep them.

## Major Changes
- Unified single and batch video compression into one workflow.
- **Added Real-ESRGAN video upscaling:**
  - Now uses the portable `realesrgan-ncnn-vulkan.exe` tool for upscaling (no Python/CUDA/PyTorch setup needed).
  - Seamless integration for high-quality video upscaling.
  - Select upscaling factor and model from the GUI.
  - Batch upscaling with per-file progress and ETA.
- Modernized all GUIs (fonts, colors, spacing, centering).
- Added scrollable progress window for batch compression and upscaling.
- Improved subtitle workflow: select which videos need subtitles before configuring options.
- Per-file progress bars and ETA in batch mode.
- Robust error handling and user feedback throughout.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest   # unit tests, plus end-to-end tests with FFmpeg (skipped when FFmpeg is not installed)
ruff check .       # lint: undefined names, unused imports and variables...
```

The tests live in `tests/`: the pure functions (bitrate budget, track ordering, ffmpeg commands, subtitle encodings, language codes...) are unit tested, and `test_ffmpeg_integration.py` runs the real ffmpeg on small generated videos (the upscaling test uses a stand-in for Real-ESRGAN). GitHub Actions runs the lint and the tests on Linux (Python 3.9 and 3.13) and Windows (Python 3.13) for every push and pull request.

## License
MIT


## Making an .exe (Windows executable)
You can create a standalone `.exe` for easy sharing and use on Windows:

1. **Install PyInstaller** (if not already installed):
   ```bash
   pip install pyinstaller
   ```


2. **Build the executable** (from the project folder, after `python scripts/fetch_deps.py`):
   ```bash
   pyinstaller --onefile --add-data "Tool;Tool" main.py
   ```
   - `--onefile`: Bundle everything into a single .exe
   - Python modules are found automatically from the imports, no need to list them.
   - `--add-data "Tool;Tool"`: embeds the Real-ESRGAN executable and model used for upscaling.

3. **Find your .exe** in the `dist` folder as `main.exe`. You can rename it if you wish.

4. **Distribute**: Share the `.exe` file with others. They do not need Python installed.

**Note:**
- If you see missing module errors, add them with more `--add-data` or check your imports.


## Changelog


### September 2026
- Repository made lighter: the Real-ESRGAN binaries and models (~72 MB) are no longer versioned, `scripts/fetch_deps.py` downloads them.
- `requirements.txt` reduced to the packages actually used (no more PyTorch/BasicSR/OpenCV), Python 3.10+ supported.
- Upscaling fixed: crash at startup, frame naming, frame rate (audio desync), x4 model scale, videos without audio, anamorphic sources, thread-safe progress window, cancellation, cleanup of temporary frames.
- Compression: the video bitrate budget now uses the re-encoded audio bitrate (192 kbps per track) instead of the source one, with a check for too small target sizes.
- Subtitle translation: fixed language codes (Chinese, Hebrew), Windows-1252 `.srt` files supported, errors reported instead of a stuck window.
- Compression and "Add subtitles": the subtitle file can be in any folder, with any name and encoding; "Add subtitles" keeps the existing subtitle tracks.
- Audio Tracks Management: MP4 output works with SRT/ASS/PGS subtitles in the source.
- Audio fix: every audio track is kept (only one was), French tracks first and default.
- Compression in two passes: the output size now matches the target (98% of it with the 2% margin, a single pass could exceed it by several %); the passes keep the source timestamps so that they encode exactly the same frames (otherwise x264 failed or hung on MKV sources), a stuck ffmpeg is killed after 5 minutes without output, and a failed encode leaves no broken file.
- ffprobe is called once per file, its errors are reported and its output is read as UTF-8 (some accented file names or titles crashed on Windows).
- Subtitle translation: each worker thread has its own translator (a shared one could give a line the translation of another line), identical lines are translated once, failed requests are retried with an increasing delay, and the translation stops with a clear message when Google keeps refusing the requests.

### July 2025
- Subtitle translation workflow now fully implemented:
  - Uses Google Translate (deep-translator) to translate all lines between any supported languages.
  - Fast, multi-threaded translation for speed.
  - Real-time progress bar in the GUI (not just command line).
  - Output saved as `_translated.srt`.
  - GUI remains responsive during translation, and a completion message is shown when done.
- **Real-ESRGAN upscaling added:**
  - Videos can now be upscaled to higher resolutions using Real-ESRGAN directly from the GUI.
  - Batch upscaling supported with per-file progress and ETA.
  - Easy model/scale selection and output management.
- Requirements updated: now uses `colorama`, `pysrt`, and `deep-translator`.
- `.gitignore` and documentation updated to reflect new modular structure and ignored files.

## Troubleshooting

- Only third-party packages (like `colorama`) are listed in `requirements.txt`. Standard Python libraries such as `os`, `subprocess`, and `tkinter` are included with every Python installation and do not need to be installed separately. If you encounter errors about missing standard libraries, your Python installation may be broken—reinstall Python from the official website to fix this.
- For upscaling, if you see errors about missing `realesrgan-ncnn-vulkan`, run `python scripts/fetch_deps.py` (add `--force` to download it again). No Python dependencies are needed for upscaling.
- On Linux, Real-ESRGAN needs a Vulkan driver (e.g. `sudo apt install libvulkan1 mesa-vulkan-drivers`).

---
Feel free to modify the project for your own needs!
