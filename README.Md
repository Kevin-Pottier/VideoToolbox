

# VideoCompress

Modern, user-friendly Python GUI for compressing one or multiple video files and translating subtitles, with per-file progress, ETA, and advanced batch features.

## Features
- Unified video compression: select one or multiple videos, all in one workflow.
- Batch mode: see all progress bars in a scrollable window, with per-file ETA.
- Modern UI: clean, dark-themed interface, clear fonts, colors, and spacing.
- Subtitle handling: for each video, choose to ignore, softcode, or hardcode subtitles.
- Efficient batch subtitle workflow: first select which videos need subtitles, then only configure those.
- Subtitle translation: translate .srt files between languages with progress feedback.
- Robust error handling and user feedback throughout.

## Requirements
- Python 3.8+
- FFmpeg and FFprobe installed and available in your system PATH
- Python packages listed in `requirements.txt`:
  - `colorama` (for colored terminal output)
  - `pysrt` (for reading/writing subtitle files)
  - `deep-translator` (for Google Translate API)
  - `tkinter` (standard library)

## Usage
1. Install requirements:
   `pip install -r requirements.txt`
2. Install FFmpeg and make sure it is in your system PATH.
3. Run the app:
   `python main.py`
4. Choose a mode:
   - Video Compression: Select one or more videos, configure subtitles, output format, and size.
   - Subtitle Translation: Translate a subtitle file between languages.

## Major Changes
- Unified single and batch video compression into one workflow.
- Modernized all GUIs (fonts, colors, spacing, centering).
- Added scrollable progress window for batch compression.
- Improved subtitle workflow: select which videos need subtitles before configuring options.
- Per-file progress bars and ETA in batch mode.
- Robust error handling and user feedback throughout.

## License
MIT

## Making an .exe out of this code
You can have a .exe out of this script to make it easier to access and share to your friends. 
1. To do so, you first need to install `pyinstaller`
```bash 
pip install pyinstaller
```
2. You can just run the following command: 
```bash
pyinstaller --onefile CompressMovie.py
```

## Changelog

### July 2025
- Subtitle translation workflow now fully implemented:
  - Uses Google Translate (deep-translator) to translate all lines from English to French.
  - Fast, multi-threaded translation for speed.
  - Real-time progress bar in the command line.
  - Output saved as `_translated.srt`.
- Requirements updated: now uses `colorama`, `pysrt`, and `deep-translator`.
- `.gitignore` and documentation updated to reflect new modular structure and ignored files.

## Troubleshooting

- Only third-party packages (like `colorama`) are listed in `requirements.txt`. Standard Python libraries such as `os`, `subprocess`, and `tkinter` are included with every Python installation and do not need to be installed separately. If you encounter errors about missing standard libraries, your Python installation may be broken—reinstall Python from the official website to fix this.

---
Feel free to modify the project for your own needs!
