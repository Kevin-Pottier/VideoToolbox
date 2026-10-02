
import collections
import contextlib
import math
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Optional
from colorama import Fore, Style
from audio_tracks import MP4_CONVERTIBLE_SUBTITLE_CODECS, ffprobe_streams, french_default_dispositions, french_first
import audio_codecs
import encoders
import hdr
from utils import COPY_INPUT_FLAGS, fps_mode_option, prepare_subtitle_file
import subprocess
# Import reusable GUI helpers for modern, DRY window/dialog creation
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label

AUDIO_BITRATE = 192000  # default bps of an audio track: used in the ffmpeg command and in the size budget
AUDIO_KBPS_CHOICES = (96, 128, 160, 192, 256)  # offered per (stereo) audio track
# Audio codecs offered by the compression (FLAC, lossless, has no predictable size), or "copy": the original
# audio kept as it is, its real bitrate counted in the size
AUDIO_CODECS = ("aac", "opus", "ac3", "eac3")
COPY_AUDIO = "copy"
# Audio codecs that MP4 can store as they are (DTS, TrueHD, PCM... need MKV)
MP4_AUDIO_CODECS = {"aac", "ac3", "eac3", "mp3", "mp2", "opus", "flac", "alac"}
MAX_HEIGHT_CHOICES = (1080, 720, 480)  # offered output heights (a smaller video keeps its own)
SIZE_MARGIN = 0.02  # share of the target size kept for the container overhead and the encoder deviation
MIN_VIDEO_BITRATE_KBPS = 100
FIRST_PASS_SHARE = 0.35  # the analysis pass is faster (x264 uses a fast first pass): share of the progress bar
STALL_TIMEOUT = 300  # seconds without any ffmpeg output after which ffmpeg is considered stuck and killed
# Consumer graphics cards limit the number of simultaneous hardware encodes: batch mode waits for a free slot
_GPU_SESSIONS = threading.BoundedSemaphore(2)


class CompressionError(Exception):
    """The compression could not be done: the message tells the user why."""


@dataclass(frozen=True)
class CompressionSettings:
    """Choices of the user besides the encoder and the size. The defaults are the former fixed values."""
    speed: str = "balanced"           # encoders.SPEEDS: the preset of the encoder
    max_height: Optional[int] = None  # a taller video is reduced to this height (the width follows)
    audio_kbps: int = AUDIO_BITRATE // 1000  # per stereo or mono track
    keep_surround: bool = False       # keep 5.1/7.1 tracks (at twice the bitrate) instead of the stereo down-mix
    audio_codec: str = "aac"          # AUDIO_CODECS, or COPY_AUDIO to keep the original audio
    hdr_to_sdr: bool = False          # convert an HDR video to SDR even with an HEVC/AV1 encoder (see hdr_mode)

    def audio(self):
        """The audio choices for audio_codecs (not for COPY_AUDIO)."""
        return audio_codecs.AudioSettings(self.audio_codec, self.audio_kbps, self.keep_surround)

    def describe(self, encoder):
        level = encoders.preset(encoder, self.speed)
        if self.audio_codec == COPY_AUDIO:
            audio = "original audio copied"
        else:
            audio = (f"audio {self.audio_codec.upper()} {self.audio_kbps} kbps per track"
                     + (", surround kept" if self.keep_surround else ", stereo"))
        return (f"speed {self.speed}" + (f" (preset {level})" if level else "")
                + (f", {self.max_height}p at most" if self.max_height else "") + f", {audio}"
                + (", HDR to SDR" if self.hdr_to_sdr else ""))


DEFAULT_SETTINGS = CompressionSettings()


def audio_bitrates(media, settings=DEFAULT_SETTINGS):
    """
    Bitrate (bps) of each audio track of the output, in the output order (French tracks first). For the
    original audio, the bitrate of the source tracks when the container gives it (see source_audio_bitrates).
    """
    tracks = french_first(media.audio_tracks)
    if settings.audio_codec == COPY_AUDIO:
        return [track.bit_rate or 0 for track in tracks]
    return audio_codecs.bitrates(tracks, settings.audio())


def source_audio_bitrates(file_path, media):
    """
    Bitrate (bps) of the audio tracks of the source, in the output order: given by ffprobe, or measured from
    the size of their packets when the container does not give it (MKV): one reading of the file.
    """
    tracks = french_first(media.audio_tracks)
    measured = {}
    if any(not track.bit_rate for track in tracks) and media.duration:
        print("Measuring the bitrate of the original audio tracks...")
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                              "packet=stream_index,size", "-of", "csv=p=0", file_path],
                             capture_output=True, encoding="utf-8", errors="replace").stdout
        sizes = collections.Counter()
        for line in out.splitlines():
            fields = line.split(",")
            if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
                sizes[int(fields[0])] += int(fields[1])
        measured = {index: int(size * 8 / media.duration) for index, size in sizes.items()}
    return [track.bit_rate or measured.get(track.stream_index, 0) for track in tracks]


def hdr_mode(media, encoder, settings=DEFAULT_SETTINGS, burn_subtitles=False):
    """
    What happens to an HDR video: "keep" (10 bits, color tags and metadata, with an HEVC or AV1 encoder) or
    "sdr" (tone mapped to BT.709: with H.264, with burned subtitles, which would be blinding in HDR, or on
    request). None for an SDR video.
    """
    video = media.video_tracks[0] if media.video_tracks else None
    if not video or not video.is_hdr:
        return None
    return "sdr" if settings.hdr_to_sdr or burn_subtitles or encoder.codec == "H.264" else "keep"


def scaled_height(media, settings=DEFAULT_SETTINGS):
    """Height the video is reduced to, or None when it keeps its own (not taller than the maximum)."""
    height = media.video_tracks[0].height if media.video_tracks else None
    if settings.max_height and height and height > settings.max_height:
        return settings.max_height
    return None


def compute_video_bitrate_kbps(max_size_gb, duration, audio_bps, margin=SIZE_MARGIN):
    """
    Video bitrate (kbps) that makes the output fit in max_size_gb, given the bitrate of all the audio tracks
    (bps) and the margin kept free. Can be negative if the size is too small.
    """
    target_bits = max_size_gb * 1024 * 1024 * 1024 * 8 * (1 - margin)  # in bits
    audio_bits_total = audio_bps * duration  # in bits
    video_bitrate = (target_bits - audio_bits_total) / duration  # in bits per second
    return int(video_bitrate / 1000)  # in kbps

def run_compression(file_path, sub_option, sub_file, ext, max_size_gb, gui_progress=None, encoder=None,
                    settings=DEFAULT_SETTINGS) -> str:
    """
    Compress a video file using FFmpeg, with optional subtitle handling and GUI/CLI progress bars.
    Args:
        file_path (str): Path to the video file.
        sub_option (str): Subtitle option ('none', 'soft', 'hard').
        sub_file (str): Path to the subtitle file (if any).
        ext (str): Output file extension ('mp4' or 'mkv').
        max_size_gb (float): Target maximum file size in GB.
        encoder (encoders.Encoder): Video encoder, x264 by default.
        settings (CompressionSettings): speed, maximum height and audio.
    Returns:
        str: path of the compressed file.
    Raises:
        CompressionError: with the reason, to show to the user (no output file is left).
    """
    encoder = encoder or encoders.DEFAULT
    # Metadata extraction (a single ffprobe call)
    try:
        media = ffprobe_streams(file_path)
    except RuntimeError as e:
        raise CompressionError(f"Could not read {os.path.basename(file_path)}: {e}") from e
    duration = media.duration
    if not duration or duration <= 0:
        raise CompressionError(f"Could not determine the duration of {os.path.basename(file_path)}.")

    # Every audio track is kept and re-encoded at the chosen bitrate (the budget depends on the number of
    # tracks, not on the source bitrate), or copied (the budget counts its real bitrate)
    n_audio_out = len(media.audio_tracks)
    if settings.audio_codec == COPY_AUDIO:
        if ext == "mp4":
            refused = sorted({track.codec for track in media.audio_tracks if track.codec not in MP4_AUDIO_CODECS})
            if refused:
                raise CompressionError(f"The {', '.join(c.upper() for c in refused)} audio cannot be copied into MP4: "
                                       "choose MKV, or an audio codec in the settings.")
        audio_bps = sum(source_audio_bitrates(file_path, media))
    else:
        audio_bps = sum(audio_bitrates(media, settings))

    print(f"Duration: {duration:.2f} s")
    print(f"Settings: {settings.describe(encoder)}")
    print(f"Audio: {n_audio_out} track(s), {audio_bps // 1000} kbps in all")

    video_bitrate_kbps = compute_video_bitrate_kbps(max_size_gb, duration, audio_bps, encoders.size_margin(encoder))

    print(f"Target Video Bitrate: {video_bitrate_kbps} kbps")
    if video_bitrate_kbps < MIN_VIDEO_BITRATE_KBPS:
        smallest_gb = ((MIN_VIDEO_BITRATE_KBPS * 1000 + audio_bps) * duration / 8
                       / (1 - encoders.size_margin(encoder)) / 1024 ** 3)
        raise CompressionError(f"Target size too small: only {max(video_bitrate_kbps, 0)} kbps would be left for the "
                               f"video (minimum {MIN_VIDEO_BITRATE_KBPS} kbps, with {n_audio_out} audio track(s), "
                               f"{audio_bps // 1000} kbps in all).\nThe smallest size for this video is "
                               f"{math.ceil(smallest_gb * 1000) / 1000:.3f} GB (or lower the audio bitrate in the "
                               "settings).")

    output_file = os.path.splitext(file_path)[0] + f"_compressed.{ext}"

    video_name = os.path.basename(file_path)
    input_path = os.path.abspath(file_path)
    output_path = os.path.abspath(output_file)
    # Temporary folder used as ffmpeg working directory: it holds the statistics of the first pass
    # and the subtitle file, copied as UTF-8 under a plain name (any location, name or encoding works)
    work_dir = tempfile.mkdtemp(prefix="videotoolbox_")
    try:
        sub_path = prepare_subtitle_file(sub_file, work_dir) if sub_option in ("soft", "hard") and sub_file else None
    except OSError as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise CompressionError(f"Cannot read the subtitle file {sub_file}: {e}") from e
    def run(passes, slot=contextlib.nullcontext()):
        for step, (cmd, _) in enumerate(passes, 1):
            print(f"\tPass {step}:", " ".join(cmd))
        print()
        try:
            with slot:
                if gui_progress is None:
                    _encode_with_progress_window(passes, duration, work_dir, video_name)
                else:
                    def report(fraction, remaining):
                        mins, secs = divmod(int(remaining), 60) if remaining is not None else (None, None)
                        gui_progress(int(fraction * 100), mins, secs)
                    _encode(passes, duration, work_dir, report)
        except CompressionError:
            if os.path.exists(output_path):
                os.remove(output_path)  # a failed encode leaves an unreadable file that looks like a result
            raise
        print(Fore.GREEN + f"\n✅ Compression finished. Output: {output_file}" + Style.RESET_ALL)

    try:
        # Shortcut: a file already under the target size only needs its streams copied (seconds, no quality
        # loss, original audio kept). Burned subtitles and a smaller resolution need a re-encode; if the copy
        # fails (codec the container cannot store), the file is encoded as usual.
        if os.path.getsize(file_path) <= max_size_gb * 1024 ** 3 * (1 - SIZE_MARGIN):
            if sub_option != "hard" and not scaled_height(media, settings):
                print(Fore.YELLOW + "\nThe file is already under the target size: copying the streams without "
                      "re-encoding\n" + Style.RESET_ALL)
                try:
                    run([(build_copy_command(input_path, output_path, ext, sub_option, sub_path, media), 1.0)])
                    return output_file
                except CompressionError:
                    print(Fore.YELLOW + "Copy impossible in this container, encoding the file instead." + Style.RESET_ALL)
            # The file was already small enough: no need to make it bigger than the source
            source_kbps = int(os.path.getsize(file_path) * 8 / duration / 1000)
            video_bitrate_kbps = min(video_bitrate_kbps, max(source_kbps, MIN_VIDEO_BITRATE_KBPS))
        metadata = None
        mode = hdr_mode(media, encoder, settings, sub_option == "hard" and bool(sub_path))
        if mode:
            video = media.video_tracks[0]
            if video.dv_profile == 5:
                raise CompressionError("This video is Dolby Vision profile 5, without an HDR10 base: its colors cannot "
                                       "be converted here (they would be wrong).")
            if mode == "sdr" and not hdr.has_zscale():
                raise CompressionError("This video is HDR: converting it to SDR needs an FFmpeg with the zscale filter "
                                       "(zimg), such as the builds of gyan.dev. Or choose an HEVC or AV1 encoder, which "
                                       "keeps the HDR.")
            if mode == "keep" and video.color_transfer == hdr.PQ:
                metadata = hdr.read_static_metadata(input_path)
            print(Fore.YELLOW + ("HDR video: kept in 10 bits" + (" with its HDR10 metadata" if metadata else "")
                                 if mode == "keep" else "HDR video: converted to SDR") + Style.RESET_ALL)
        passes = build_encode_commands(input_path, output_path, ext, video_bitrate_kbps, sub_option, sub_path, work_dir,
                                       media, fps_mode_option(), encoder, settings, metadata)
        print(Fore.YELLOW + f"\nRunning ffmpeg ({encoder.label}, {len(passes)} pass(es)) with subtitles option: "
              f"{sub_option}\n" + Style.RESET_ALL)
        run(passes, _GPU_SESSIONS if encoder.hardware else contextlib.nullcontext())
        return output_file
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def output_streams(media, ext, added_subtitle):
    """
    -map, -disposition and subtitle codec arguments, the same for an encode and a copy. The output keeps:
    - the main video
    - every audio track, the French ones first; the first French track becomes the default one
      (the other disposition flags, e.g. audio description, are kept)
    - the subtitle file added as soft subtitles (second input): first, and default
    - the subtitles of the source that the container can store (MP4: text subtitles only), and
      in MKV the attachments (fonts of ASS subtitles)
    """
    args = ["-map", "0:v:0"]
    audio_tracks = french_first(media.audio_tracks)
    for track in audio_tracks:
        args += ["-map", f"0:{track.stream_index}"]
    args += french_default_dispositions(audio_tracks)
    subtitles = [("1:0", None)] if added_subtitle else []
    for track in media.subtitle_tracks:
        if ext == "mp4" and track.codec not in MP4_CONVERTIBLE_SUBTITLE_CODECS:
            print(Fore.YELLOW + f"Subtitle track {track.stream_index} ({track.codec}) skipped: MP4 cannot store it, "
                  "choose MKV to keep it." + Style.RESET_ALL)
            continue
        subtitles.append((f"0:{track.stream_index}", track.codec))
    for spec, _ in subtitles:
        args += ["-map", spec]
    if added_subtitle:
        for i in range(len(subtitles)):
            args += [f"-disposition:s:{i}", "default" if i == 0 else "0"]
    if subtitles:
        # mov_text is the only text subtitle codec of MP4; MKV takes the others as they are, but not mov_text
        args += ["-c:s", "mov_text" if ext == "mp4" else "copy"]
        if ext == "mkv":
            for i, (_, codec) in enumerate(subtitles):
                if codec == "mov_text":
                    args += [f"-c:s:{i}", "srt"]
    if ext == "mkv":
        args += ["-map", "0:t?", "-c:t", "copy"]
    return args


def audio_args(media, settings=DEFAULT_SETTINGS):
    """Audio arguments: the chosen codec and bitrate, stereo or surround kept (see audio_codecs), or a copy."""
    if settings.audio_codec == COPY_AUDIO:
        return ["-c:a", "copy"]
    return audio_codecs.encode_args(french_first(media.audio_tracks), settings.audio())


def build_encode_commands(input_path, output_path, ext, video_bitrate_kbps, sub_option, sub_path, work_dir, media,
                          fps_mode="-fps_mode", encoder=encoders.DEFAULT, settings=DEFAULT_SETTINGS,
                          hdr_metadata=None):
    """
    ffmpeg commands that encode the video at the bitrate that fits the target size.
    Two-pass encoders (x264, x265) first analyse the video, then use these statistics to distribute
    the bits and hit the target size precisely; the other encoders (GPU, SVT-AV1) use a single pass.
    Both passes must encode exactly the same frames: the timestamps are passed through, otherwise
    the MP4 output of the second pass can duplicate a frame that the first pass did not analyse
    (x264 then fails with "Incomplete MB-tree stats file" or even hangs).
    media is the audio_tracks.MediaFileInfo of the input, fps_mode the option name given by utils.fps_mode_option(),
    settings the CompressionSettings (preset, maximum height, audio), hdr_metadata the hdr.StaticMetadata of
    an HDR10 source whose HDR is kept (see hdr_mode).
    Returns:
        list: (command, share of the total work) for each pass.
    """
    mode = hdr_mode(media, encoder, settings, sub_option == "hard" and bool(sub_path))
    filters = [hdr.TONEMAP_FILTER] if mode == "sdr" else []
    height = scaled_height(media, settings)
    if height:
        filters.append(f"scale=-2:{height}:flags=lanczos")  # the width follows (even), the aspect ratio is kept
    if sub_option == "hard" and sub_path:
        # After the resize: the subtitles are drawn at the output resolution, sharp.
        # Plain relative subtitle name, resolved in the working directory: no filter escaping needed
        filters.append(f"subtitles={os.path.basename(sub_path)}")
    video_args = [*encoders.filter_args(encoder, filters, ten_bit=mode == "keep"), fps_mode, "passthrough",
                  *encoders.bitrate_args(encoder, video_bitrate_kbps, settings.speed)]
    x265_hdr = []
    if mode == "keep":
        video = media.video_tracks[0]
        video_args += [*encoders.ten_bit_args(encoder), *hdr.tags(video)]
        if encoder.name == "libx265":
            x265_hdr = hdr.x265_params(video, hdr_metadata)
        elif encoder.name == "libsvtav1":
            video_args += hdr.svtav1_params(hdr_metadata)
    elif mode == "sdr":
        video_args += hdr.SDR_TAGS
    hw_input = encoders.input_args(encoder)
    soft = sub_option == "soft" and bool(sub_path)
    inputs = [*hw_input, "-i", input_path, *(["-i", sub_path] if soft else [])]
    streams = output_streams(media, ext, soft)
    audio = audio_args(media, settings)
    output_args = [*video_args, *audio, *streams, "-movflags", "+faststart", output_path]
    if not encoder.two_pass:
        return [(["ffmpeg", "-y", *inputs, *output_args], 1.0)]

    def pass_args(number):
        if encoder.name == "libx265":
            # Relative statistics file, in the working directory: x265-params uses ':' as separator
            return ["-x265-params", ":".join([f"pass={number}", "stats=x265_2pass.log", "log-level=error", *x265_hdr])]
        return ["-pass", str(number), "-passlogfile", os.path.join(work_dir, "ffmpeg2pass")]

    # Both passes encode the same video stream (the first one, as in output_streams)
    pass1 = ["ffmpeg", "-y", *hw_input, "-i", input_path, "-map", "0:v:0", *video_args, *pass_args(1),
             "-an", "-sn", "-f", "null", "-"]
    pass2 = ["ffmpeg", "-y", *inputs, *video_args, *pass_args(2), *audio, *streams,
             "-movflags", "+faststart", output_path]
    return [(pass1, FIRST_PASS_SHARE), (pass2, 1 - FIRST_PASS_SHARE)]


def build_copy_command(input_path, output_path, ext, sub_option, sub_path, media):
    """
    ffmpeg command that copies the streams without re-encoding (for a file already under the target size),
    with the same streams and order as an encode (see output_streams).
    """
    soft = sub_option == "soft" and bool(sub_path)
    cmd = ["ffmpeg", "-y", *COPY_INPUT_FLAGS, "-i", input_path, *(["-i", sub_path] if soft else []), "-c", "copy",
           *output_streams(media, ext, soft)]
    if ext == "mp4":
        cmd += ["-movflags", "+faststart"]
    return cmd + [output_path]


def _encode(passes, duration, work_dir, report):
    """
    Run the passes one after the other; report(fraction of the whole job, seconds left or None)
    is called on each ffmpeg progress line. Raises CompressionError if ffmpeg fails.
    """
    start_time = time.time()
    done = 0.0
    for step, (cmd, share) in enumerate(passes, 1):
        # ffmpeg writes UTF-8 (file names): the locale encoding (cp1252 on Windows) could fail on it
        proc = subprocess.Popen(cmd, cwd=work_dir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace")
        last_lines = collections.deque(maxlen=8)  # shown if ffmpeg fails
        last_output = [time.time()]
        stalled = threading.Event()

        def watchdog():
            # A stuck ffmpeg ignores the usual termination request: kill it
            while proc.poll() is None:
                if time.time() - last_output[0] > STALL_TIMEOUT:
                    stalled.set()
                    proc.kill()
                    return
                time.sleep(1)
        threading.Thread(target=watchdog, daemon=True).start()
        for line in proc.stderr:  # progress lines end with \r, split like \n
            last_output[0] = time.time()
            last_lines.append(line.rstrip())
            match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
            if match:
                h, m, s = match.groups()
                fraction = done + share * min(1.0, (int(h) * 3600 + int(m) * 60 + float(s)) / duration)
                elapsed = time.time() - start_time
                report(fraction, elapsed / fraction - elapsed if fraction > 0 else None)
        proc.wait()
        if proc.returncode != 0:
            reason = f"ffmpeg stopped responding for {STALL_TIMEOUT} s and was killed" if stalled.is_set() else "\n".join(last_lines)
            print(Fore.RED + f"\n❌ Compression failed (pass {step}):\n{reason}" + Style.RESET_ALL)
            raise CompressionError(f"ffmpeg failed (pass {step}):\n{reason}")
        done += share
    report(1.0, 0)


def _encode_with_progress_window(passes, duration, work_dir, video_name):
    """Encode in a worker thread while a progress window (and a console bar) shows the progress. Raises CompressionError."""
    import tkinter as tk
    import tkinter.ttk as ttk
    events = queue.Queue()  # the worker thread never touches Tk: it only fills this queue
    # The error of the worker thread, raised in the calling thread
    result = {"error": CompressionError("The compression stopped unexpectedly (see the console).")}

    root = tk._default_root
    progress_win = tk.Toplevel(root) if root is not None and root.winfo_exists() else tk.Tk()
    progress_win.title("Compression Progress")
    progress_win.geometry("420x150")
    progress_win.attributes('-topmost', True)
    apply_modern_theme(progress_win)
    frame = create_styled_frame(progress_win)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    create_styled_label(frame, text=f"Compressing: {video_name}", style='Title.TLabel').pack(pady=(0, 8))
    progress_var = tk.DoubleVar(master=progress_win)
    ttk.Progressbar(frame, variable=progress_var, maximum=100, length=350, style='TProgressbar').pack(pady=6)
    percent_label = create_styled_label(frame, text="0%", style='TLabel')
    percent_label.pack()
    time_label = create_styled_label(frame, text="Estimated time left: --:--", style='TLabel', font=("Segoe UI", 10, "italic"))
    time_label.pack()

    def show(fraction, remaining):
        percent = int(fraction * 100)
        eta = "--:--" if remaining is None else "{:02d}:{:02d}".format(*divmod(int(remaining), 60))
        progress_var.set(percent)
        percent_label.config(text=f"{percent}%")
        time_label.config(text=f"Estimated time left: {eta}")
        bar_len = 40
        filled = int(round(bar_len * fraction))
        sys.stdout.write(f"\rCompressing: [{'=' * filled}{'-' * (bar_len - filled)}] {percent}% | ETA: {eta}")
        sys.stdout.flush()

    def worker():
        error = result["error"]
        try:
            _encode(passes, duration, work_dir, lambda *progress: events.put(("progress", *progress)))
            error = None
        except CompressionError as e:
            error = e
        finally:
            events.put(("done", error))

    def poll():
        try:
            while True:
                event = events.get_nowait()
                if event[0] == "progress":
                    show(*event[1:])
                else:
                    print()
                    result["error"] = event[1]
                    progress_win.after(500, progress_win.destroy)
                    return
        except queue.Empty:
            pass
        progress_win.after(200, poll)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    poll()
    progress_win.wait_window()
    thread.join()
    if result["error"] is not None:
        raise result["error"]
