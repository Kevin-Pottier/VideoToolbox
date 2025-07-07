
# CompressMovie

> This repository now uses a modular Python project structure for video compression and subtitle translation using FFmpeg.

## Features
- Modular codebase: main logic is split into `main.py`, `gui_film.py`, `gui_subtitle.py`, `compression.py`, and `utils.py`.
- Choose usage mode at launch: Film Compression or Subtitle Translation (via a GUI dialog).
- For Film Compression:
  - Select a video file via a GUI dialog (supports .mp4, .mkv, .avi)
  - Choose subtitle options via a dedicated dialog: no subtitles, softcode (attach .srt), or hardcode (burn in). If you select a subtitle option but do not choose a file, you will be prompted again.
  - Choose output container (MP4 or MKV) via a dialog
  - Enter the maximum output file size (in GB) via a dialog
  - Uses relative subtitle paths for better FFmpeg compatibility
  - Automatically calculates the required video bitrate for your target size
  - Runs FFmpeg directly (no batch file needed)
  - Shows the FFmpeg command used
- For Subtitle Translation:
  - Select a subtitle file to translate via a dialog
  - Translates all subtitle lines from English to French using Google Translate (deep-translator)
  - Fast translation using parallel requests (multi-threaded)
  - Shows a real-time progress bar in the command line during translation
  - Saves the translated subtitle as a new file with `_translated.srt` suffix

## Requirements
- Python 3
- FFmpeg and FFprobe installed and available in your system PATH
- Python packages listed in `requirements.txt`:
  - `colorama` (for colored terminal output)
  - `pysrt` (for reading/writing subtitle files)
  - `deep-translator` (for Google Translate API)

All required Python packages can be installed with:

```bash
pip install -r requirements.txt
```

## Usage
1. Run the script:
   `python main.py`
2. Choose the usage mode:
   - **Film Compression**: Compress a video file with optional subtitles.
   - **Subtitle Translation**: Select a subtitle file for translation (English to French, with progress bar).
3. Follow the dialogs for your chosen mode:
   - For Film Compression:
     - Select a video file.
     - Choose subtitle options (none, softcode, hardcode). If you select softcode or hardcode, you must also select a subtitle file.
     - Choose the output container (MP4 or MKV).
     - Enter the maximum output file size (in GB).
     - The script will extract video/audio metadata, calculate the required video bitrate, and run FFmpeg to compress the video.
     - The output video will be created in the same folder as the original.
   - For Subtitle Translation:
     - Select a subtitle file (`.srt` or `.ass`).
     - The script will translate all lines from English to French using Google Translate (deep-translator).
     - A real-time progress bar will be shown in the command line.
     - The translated subtitle will be saved as a new file with `_translated.srt` appended to the name.

- Only `.py`, `.gitignore`, `README.Md`, and `requirements.txt` are tracked by git (see `.gitignore`).
- All other files (videos, batch files, outputs, and the old `CompressMovie.py`) are ignored by git.

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
