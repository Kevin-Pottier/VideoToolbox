

# VideoCompress

Modern, user-friendly Python GUI for compressing or upscaling one or multiple video files and translating subtitles, with per-file progress, ETA, advanced batch features, and a fast, responsive, multi-threaded subtitle translation workflow with GUI progress bar. Now includes Real-ESRGAN integration for high-quality video upscaling.

## Features
- Unified video compression and upscaling: select one or multiple videos, all in one workflow.
- **Real-ESRGAN upscaling**: upscale videos to higher resolutions using state-of-the-art AI (Real-ESRGAN). Choose upscaling factor and model.
- Batch mode: see all progress bars in a scrollable window, with per-file ETA.
- Modern UI: clean, dark-themed interface, clear fonts, colors, and spacing.
- Subtitle handling: for each video, choose to ignore, softcode, or hardcode subtitles.
- Efficient batch subtitle workflow: first select which videos need subtitles, then only configure those.
- Subtitle translation: translate .srt files between languages with a fast, multi-threaded workflow, real-time GUI progress bar, and completion notification.
- Robust error handling and user feedback throughout.

## Requirements

- Python 3.8–3.9 (for advanced features; not compatible with Python 3.10+)
- FFmpeg and FFprobe installed and available in your system PATH
- **No need to install Real-ESRGAN Python dependencies or external repo!**
- The upscaling feature now uses the portable `realesrgan-ncnn-vulkan.exe` tool (included in the `Tool/` folder), which works out-of-the-box on Windows and leverages your GPU automatically.
- Python packages listed in `requirements.txt`:
  - `colorama` (for colored terminal output)
  - `pysrt` (for reading/writing subtitle files)
  - `deep-translator` (for Google Translate API)
  - `tkinter` (standard library)

## Usage

0. Clone the repo using: 
   ```bash
   git clone https://github.com/Kevin-Pottier/VideoCompress.git
   ```
1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Install FFmpeg and make sure it is in your system PATH.
3. **Upscaling is ready out-of-the-box!** The `Tool/realesrgan-ncnn-vulkan.exe` executable is included and does not require any Python or CUDA setup. No need to install or configure anything else for upscaling.
4. Run the app:
   ```bash
   python main.py
   ```
5. Choose a mode:
   - **Video Compression**: Select one or more videos, configure subtitles, output format, and size. Batch mode shows a scrollable window with per-file progress and ETA.
   - **Video Upscaling (Real-ESRGAN)**: Select one or more videos to upscale. Choose upscaling factor (e.g., 2x, 4x) and model. Progress bars and ETA are shown for each file. Output is saved in the selected folder.
   - **Subtitle Translation**: Translate a subtitle file between languages. The translation is fast (multi-threaded), the GUI remains responsive, and a progress bar shows real-time status. When finished, a message box confirms completion and the window closes automatically.

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

## License
MIT


## Making an .exe (Windows executable)
You can create a standalone `.exe` for easy sharing and use on Windows:

1. **Install PyInstaller** (if not already installed):
   ```bash
   pip install pyinstaller
   ```


2. **Build the executable** (from the project folder):
   ```bash
   pyinstaller --onefile --add-data "main.py;." --add-data "gui_helpers.py;." --add-data "gui_film.py;." --add-data "gui_subtitle.py;." --add-data "compression.py;." --add-data "utils.py;." main.py
   ```
   - `--onefile`: Bundle everything into a single .exe
   - `--add-data "<file.py>;."`: Ensures each Python module is included (repeat for all .py files in the project)
   - If you use additional data files (like themes), add them with more `--add-data` options.

3. **Find your .exe** in the `dist` folder as `main.exe`. You can rename it if you wish.

4. **Distribute**: Share the `.exe` file with others. They do not need Python installed.

**Note:**
- If you see missing module errors, add them with more `--add-data` or check your imports.


## Changelog


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
- If you see errors related to Real-ESRGAN or its dependencies, make sure you are using Python 3.8 or 3.9. Real-ESRGAN is not compatible with Python 3.10 or newer.
- For upscaling, if you see errors about missing `realesrgan-ncnn-vulkan.exe`, make sure the `Tool/` folder is present and contains the executable. No Python dependencies are needed for upscaling.

---
Feel free to modify the project for your own needs!
