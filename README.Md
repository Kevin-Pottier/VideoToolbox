# CompressMovie

>This repository contains a simple Python script to compress video files to a target size using FFmpeg.

## Features
- Select a video file via a GUI dialog (supports .mp4, .mkv, .avi)
- Choose output container (MP4 or MKV)
- Enter the maximum output file size (in GB) via a dialog
- Choose subtitle options via a dedicated dialog: no subtitles, softcode (attach .srt), or hardcode (burn in). If you select a subtitle option but do not choose a file, you will be prompted again.
- Uses relative subtitle paths for better FFmpeg compatibility
- Automatically calculates the required video bitrate for your target size
- Runs FFmpeg directly (no batch file needed)
- Shows the FFmpeg command used

## Requirements
- Python 3
- FFmpeg and FFprobe installed and available in your system PATH
- Python packages listed in `requirements.txt`
- `colorama` (optional, for colored terminal output)

All required Python packages can be installed with:

```bash
pip install -r requirements.txt
```

## Usage
1. Run `CompressMovie.py` with Python 3.
2. Select your video file in the dialog.
3. Choose the output format (MP4 or MKV).
4. Enter the maximum output file size (in GB) when prompted.
5. Choose subtitle options (no subtitles, softcode, or hardcode) and select a subtitle file if needed.
6. The script will run FFmpeg directly to compress your video to the target size.
7. The output file will be created in the same folder as the original video.

- Only `.py`, `.gitignore`, and `README.Md` are tracked by git (see `.gitignore`).
- All other files (videos, batch files, outputs) are ignored by git.

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

## Troubleshooting

- Only third-party packages (like `colorama`) are listed in `requirements.txt`. Standard Python libraries such as `os`, `subprocess`, and `tkinter` are included with every Python installation and do not need to be installed separately. If you encounter errors about missing standard libraries, your Python installation may be broken—reinstall Python from the official website to fix this.

---
Feel free to modify the script for your own needs!
