

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
2. Download the external tools and check that FFmpeg is installed (the official Real-ESRGAN archive, ~45 MB, is SHA-256 checked and only the files the app uses are kept). Run it again after an update of VideoToolbox: it adds the models that are missing:
   ```bash
   python scripts/fetch_deps.py
   ```
   If FFmpeg is missing, the script tells you how to install it (e.g. `winget install Gyan.FFmpeg` on Windows).
3. Run the app:
   ```bash
   python main.py
   ```
4. Choose a mode:
   - **Video Compression**: Select one or more videos, configure subtitles, output format, encoder (see [Video encoders](#video-encoders)), settings and size. The settings: the speed / quality trade-off (Fast, Balanced, Best quality: the preset of the encoder), a maximum resolution (1080p, 720p or 480p at most: for a small size, a lower resolution gives a sharper picture than a full resolution starved of bitrate; smaller videos keep their own) and the audio: the codec (AAC, Opus, AC3, E-AC3, see [Audio conversion](#usage)) with its bitrate per track from 96 to 256 kbps and the 5.1/7.1 surround kept at twice the bitrate or down-mixed to stereo, or the original audio kept as it is (copied without loss, its real size counted; MP4 cannot store some codecs such as DTS: choose MKV). The defaults (Balanced, resolution kept, 192 kbps stereo) are the former fixed values. With x264/x265 the video is encoded in two passes (an analysis pass, then the real encode) so that the file ends up just under the requested size. Every audio track is kept (re-encoded to stereo AAC at 192 kbps each, counted in the size), French tracks first and default, as well as the subtitle tracks of the source (in MP4, only the text ones); added soft subtitles become the first, default subtitle track. A file that is already under the requested size is only remuxed (streams copied in a few seconds, no quality loss, original audio kept). HDR videos (HDR10, HLG, Dolby Vision with an HDR10 base) keep their HDR with an HEVC or AV1 encoder (10 bits, color tags, and with x265 and SVT-AV1 the HDR10 metadata of the source), and are converted to SDR (tone mapping, the colors stay right on every screen) with H.264, with burned subtitles, or on request; the settings show the choice when one of the videos is HDR. Dolby Vision profile 5 (no HDR10 base) is refused. If the compression cannot be done (size too small, with the smallest possible size for the video, unreadable file, ffmpeg error), a message says why. Batch mode shows a scrollable window with per-file progress and ETA.
   - **Video Upscaling (Real-ESRGAN)**: Select one or more videos to upscale, the target resolution (720p, 1080p, 4K), the model and the encoder:
     - **Live action** (`realesrgan-x4plus`): the best quality, slow (x4, then resized to the target height). From a 1080p source, each frame is computed at 7680x4320: with an integrated GPU it takes minutes per frame, far too long for a movie: prefer the animation model or a dedicated graphics card.
     - **Animation** (`realesr-animevideov3`): about 10 times faster, designed for cartoons and anime, with native x2/x3/x4 networks (the smallest one that reaches the target is used).
     
     The frames go through a pipeline: ffmpeg decodes them (lossless PNG) while Real-ESRGAN upscales the previous chunk on the GPU and the encoder compresses the chunk before, so the total time is close to the time of the slowest stage, and only a few chunks of frames are on the disk at once (a few GB instead of hundreds for a movie). The aspect ratio, frame rate and audio are kept. Before starting, the temporary disk space needed is shown with the free space, and the upscaling can be cancelled (if the space is not enough, "No" is the default answer). A progress window shows the progress, the time left, the frame in progress and the time per frame; the progress inside a frame is followed tile by tile, so the time left appears after the first tiles of the first frame, even when a frame takes several minutes (closing the window cancels). AI upscaling is most useful for SD sources (DVD); from 720p or 1080p, the gain over a classic resize is smaller.
   - **Subtitle Translation**: Translate one or more `.srt` files (UTF-8 or Windows-1252) between languages. The translation is fast (multi-threaded), the GUI remains responsive, and a progress bar shows real-time status. When finished, a message box confirms completion (and reports the lines that could not be translated) and the window closes automatically.
   - **Audio conversion**: Convert every audio track of one or more videos without re-encoding the video: the codec (AAC, plays everywhere; Opus, the best quality per kbps; AC3 or E-AC3 for home cinemas and TVs; FLAC, lossless: only the codecs of your FFmpeg build are offered), the bitrate per track (96 to 320 kbps, twice for the 5.1/7.1 tracks kept) and stereo (down-mix) or the channels kept (AC3/E-AC3: 5.1 at most, a 7.1 track is down-mixed to 5.1 with its LFE). For example, the AC3 track of a DivX movie to AAC, in a few seconds. All tracks, subtitles and attachments are kept; French audio tracks are moved first and the first one becomes the default track (detected from the language tag, or from titles such as `VFF`/`VFQ`). The output is written next to the video (`film_aac.mkv`, `film_opus.mp4`...): MP4/MOV stay MP4/MOV, other files (AVI...) and FLAC go to MKV. The default (AAC 160 kbps stereo) is the former "Audio fix for stereo".
   - **Add subtitles**: Add a subtitle file (`.srt`/`.ass`, from any folder, any encoding) as a new track, keeping the existing ones, or burn it into the video.
   - **Audio Tracks Management**: Choose which audio tracks to keep and the default one. For MP4 output, text subtitles are converted to `mov_text` and image subtitles (PGS, DVD) are skipped: choose MKV to keep them.

## Video encoders

The compression asks which encoder to use. Only the encoders that work on the computer are offered: FFmpeg lists the GPU encoders it was built with even without the matching card, so each one is tried on a few test frames first (GPU encoders are listed first).

| Encoder | Runs on | Speed | Quality for a given size | Size | The file plays on |
|---|---|---|---|---|---|
| **H.264 - x264** | CPU | reference | good | exact (2 passes) | everything |
| **HEVC - x265** | CPU | slower than x264 | better (≈ same quality with a smaller file) | exact (2 passes) | most devices since ~2016, VLC |
| **AV1 - SVT-AV1** | CPU | faster than x264 on recent CPUs | best | approximate (1 pass) | recent devices (~2020+), browsers, VLC |
| **H.264 - GPU** | graphics card | very fast | good (slightly below x264 on older cards) | approximate (1 pass) | everything |
| **HEVC - GPU** | graphics card | very fast | better than H.264 | approximate (1 pass) | most devices since ~2016, VLC |
| **AV1 - GPU** | recent graphics card | very fast | best | approximate (1 pass) | recent devices, VLC |

Presets used for the speed / quality setting of the compression (Balanced was the only one before):

| Encoder | Fast | Balanced | Best quality |
|---|---|---|---|
| x264 | veryfast | medium | slower |
| x265 | veryfast | medium | slow |
| SVT-AV1 | preset 10 | preset 8 | preset 6 |
| NVIDIA NVENC | p3 | p5 | p7 |
| AMD AMF | speed | balanced | quality |
| Intel Quick Sync | faster | slow | veryslow |
| VAAPI, Apple VideoToolbox | no preset: the three are the same | | |

"Approximate" means the size is usually within a few % of the target (a 5% margin is kept); two passes hit it precisely (2% margin).

GPU encoders by graphics card (the FFmpeg builds of gyan.dev, installed by `winget install Gyan.FFmpeg`, include all of them on Windows):

| Card | Encoder | H.264 | HEVC | AV1 |
|---|---|---|---|---|
| NVIDIA | NVENC | GTX 600 and later | GTX 950/960 and later (e.g. RTX 2060: H.264 + HEVC) | RTX 40 and later |
| AMD | AMF (Windows) | HD 7000 and later | RX 400 and later | RX 7000 and later |
| Intel | Quick Sync | 2nd gen Core and later | 6th gen Core and later | Arc, Core Ultra |
| Intel / AMD on Linux | VAAPI | depends on the driver | | |
| Mac | VideoToolbox | yes | yes | no |

See [Metrics](#metrics) for measurements on real footage. The x264 presets change little (veryfast: +24% speed, lower quality; slow: no gain on a 720p test clip). GPU encoders could not be measured there: they are typically about ten times faster than x264.

To compare the encoders on your own computer and video:

```bash
python scripts/benchmark_encoders.py my_movie.mkv --start 300 --duration 30 --kbps 2500
```

It encodes the same extract with every working encoder, using the commands of the compression mode, and prints the speed (frames per second and times faster than real time), the quality compared with the extract (SSIM, PSNR, and VMAF when FFmpeg includes it) and the size compared with the target. Choose a `--kbps` lower than the bitrate of the source (a warning tells when it is not): with more bits than they need, all the encoders give the quality of the source and the comparison shows nothing. A video shorter than `--start` + `--duration` is measured from its end.

## Metrics

Measured in October 2026 on a cloud virtual machine: 4 x86-64 vCPU, 15 GB of RAM, **no GPU**, FFmpeg 6.1.1, with real footage: a 1080p30 camera video ([intel-iot-devkit/sample-videos](https://github.com/intel-iot-devkit/sample-videos), `classroom.mp4`) and the *Megamind* trailer (720x528 DivX AVI, [OpenCV samples](https://github.com/opencv/opencv/tree/4.x/samples/data)). A desktop CPU is faster, and the GPU encoders could not be measured: run `scripts/benchmark_encoders.py` on your own computer and video to get your figures.

### Compression: speed and quality of the encoders

1080p30 real footage, 30 s extract, measured with `scripts/benchmark_encoders.py` (SSIM in dB against the extract, higher is better: 20 dB = 0.990, 23 dB = 0.995):

| Encoder | Speed (frames/s) | SSIM at 2000 kbps | SSIM at 1000 kbps | A 2 h 1080p movie (24 fps) on these 4 vCPU |
|---|---|---|---|---|
| H.264 - x264 (2 passes) | 33 to 41 | 22.20 dB | 20.49 dB | ≈ 1 h 30 |
| HEVC - x265 (2 passes) | 14 to 16 | 22.67 dB | 21.37 dB | ≈ 3 h 25 |
| AV1 - SVT-AV1 (1 pass) | 26 to 30 | 23.16 dB | 22.18 dB | ≈ 1 h 50 |

- **SVT-AV1 at 1000 kbps gives the quality of x264 at 2000 kbps** (22.18 vs 22.20 dB): the same quality in a file half the size, and almost twice as fast as x265.
- SD movie (*Megamind* trailer, 800 kbps): x264 106 frames/s (4.5 times faster than real time: a 2 h DVD movie in about 30 min), SVT-AV1 57, x265 34; at this bitrate the three give the same quality (SSIM 16.72, 16.80 and 16.81 dB).

### Compression: size of the output

Whole files compressed through the application (33 s 1080p movie with two audio tracks, target 0.008 GB):

| Encoder | Output size / target |
|---|---|
| x264, 2 passes | 98.6 % |
| x265, 2 passes | 97.3 % |
| SVT-AV1, 1 pass | 92.7 % |

In these runs the output never exceeded the target. A file already under the target is only remuxed: a few seconds whatever its length, without quality loss.

### Upscaling

- Temporary disk space for a 2 h movie upscaled x4 (estimate of the application): **3.5 GB with the pipeline**, instead of 507 GB (DVD, 720x480) or 1,352 GB (720p) when every frame was extracted before the upscale.
- The animation model (`realesr-animevideov3`) was about 10 times faster than `realesrgan-x4plus` on the same frames (7.5 s vs 79 s, CPU through software Vulkan; a GPU is much faster for both).

### Repository and tests

- Fresh clone: **74 MB → 0.18 MB** (the Real-ESRGAN binaries and models are downloaded by `scripts/fetch_deps.py` instead of being versioned).
- 250 automated tests (unit, real FFmpeg on generated videos, compression workflow without display), run by GitHub Actions on Linux (Python 3.9 and 3.13) and Windows: they cover 74 % of the processing code (compression, encoders, audio, subtitles); the windows are covered by the end-to-end battery below.
- End-to-end battery (`tests/e2e/run.py`, see [Development](#development)): 27 scenarios driven through the real windows from the main menu, on real footage: compression (no subtitles, soft, burned, MP4 and MKV, x264/x265/SVT-AV1, settings, original audio kept, copy shortcut, batch, invalid and too small sizes, cancellation), translation (single and batch with a stand-in for Google, which refuses the requests of a cloud machine, invalid file, Google refusing the requests), upscaling with the real Real-ESRGAN (both models, refusal at the disk space question), audio conversion (AAC, Opus 5.1, DivX AVI), add subtitles (soft, burned, DivX AVI, batch) and audio tracks management. It found three of the bugs fixed in October 2026 (see the changelog).

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

End-to-end battery: every feature driven through its real windows, from the main menu, on real footage, with the outputs checked by ffprobe (streams, sizes, frames, audio tracks, burned subtitles...):

```bash
python tests/e2e/run.py                  # every scenario: a few minutes, plus the upscaling
python tests/e2e/run.py compress audio   # the scenarios whose name starts with these words
python tests/e2e/run.py --list
```

The windows open and are clicked automatically: do not use the mouse or the keyboard meanwhile (on Linux without display, it runs in `xvfb-run`). The test videos (about 15 MB) are downloaded on the first run into the temporary folder of the system (not into the project, which may be synchronized by OneDrive), where the outputs of each scenario stay for inspection (`videotoolbox_e2e/work/`, the path is printed at the end). Scenarios that cannot run on the computer are skipped: GPU encoder without GPU, upscaling without Real-ESRGAN, Google Translate refusing the requests. Run it after a change, and on a computer with a GPU to test its encoder and the upscaling at full speed.

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


### October 2026
- HDR videos: an HDR10/HLG movie compressed in H.264 became an 8-bit video still tagged as HDR (washed-out colors on most screens). The HDR is now kept with HEVC/AV1 (10 bits, color tags, HDR10 metadata with x265 and SVT-AV1), and converted to SDR with H.264, burned subtitles or on request.
- "Audio fix for stereo" becomes "Audio conversion": choice of the codec (AAC, Opus, AC3, E-AC3, FLAC), of the bitrate and of stereo or the channels kept, the video still copied. The 5.1(side) layout of DTS/AC3 tracks (refused by Opus, unknown for AAC) and the 7.1 tracks going to AC3/E-AC3 (which made them 5.0 without LFE) are converted to standard layouts; AVI sources and FLAC go to MKV, and the MP4 subtitles are converted for it.
- Compression: choice of the audio codec (AAC, Opus, AC3, E-AC3), or the original audio kept as it is (copied without loss, its real bitrate counted in the size, measured when the container does not give it; refused with a clear message when MP4 cannot store it).
- Compression settings ([issue #2](https://github.com/Kevin-Pottier/VideoToolbox/issues/2)): speed / quality (the preset of each encoder), maximum resolution, audio bitrate per track and 5.1/7.1 kept or down-mixed to stereo; the size budget follows the audio choices. A file already under the target that must be reduced in resolution (or get burned subtitles) is encoded at the bitrate of the source at most, never bigger.
- Compression without subtitles works again: it stopped with "Unable to determine the subtitle file" (regression of the PyCharm warnings fix).
- Compression keeps every audio track, French first and default, whatever the subtitle option: without subtitles or with burned ones, ffmpeg kept a single track (the English one of a VF/VO movie). The subtitle tracks of the source are kept too.
- Compression errors are shown in a message box (they were only printed in the console, the window closed as if everything had worked); batch mode lists the failed videos.
- Upscaling: the temporary disk space needed is always shown before starting, with the free space, and the upscaling can be refused (it was only asked when the space was missing). The time left follows the progress inside each frame (tile by tile), with the frame in progress and the time per frame: with the live action model on a 1080p source and an integrated GPU, nothing moved before the first frame was finished, after more than 10 minutes.
- The end-to-end battery (`tests/e2e/run.py`) is part of the project.
- AVI files of DivX/XviD movies (MPEG-4 with B-frames): adding subtitles, the audio tracks management to MKV and the copy shortcut of the compression failed ("Can't write packet with unknown timestamp"); the missing timestamps are now generated. When the copy shortcut is impossible anyway, the encode no longer makes the file bigger than the source, and a failed ffmpeg no longer leaves a broken file behind (add subtitles, audio tracks, audio fix).

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
- Upscaling: choice of the model (live action, or the animation video model about 10 times faster) and of the encoder, frames processed as a pipeline in chunks (decoding, Real-ESRGAN and encoding at the same time, a few GB of temporary files instead of hundreds), Real-ESRGAN 0.2.5.0 (run `python scripts/fetch_deps.py` again).
- Compression: choice of the video encoder (x264, x265, SVT-AV1, and the GPU encoders of NVIDIA, AMD, Intel and Apple, detected automatically), `scripts/benchmark_encoders.py` to compare them, and a file already under the target size is only remuxed.
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
