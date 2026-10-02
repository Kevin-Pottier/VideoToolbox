"""
Windows shared by the features of VideoToolbox.

Every window is a Toplevel of one hidden Tk root (app_root): a second tk.Tk() would be a second Tcl interpreter,
whose widgets and variables cannot be mixed with those of the first one. A dialog waits with wait_window until it
is closed; closing it with the window button cancels.

run_jobs runs the work (compressions, conversions...) in worker threads while a window shows a bar and the time
left for each job: the worker threads never touch Tk, their progress goes through a queue.
"""
import os
import queue
import threading
import tkinter as tk
from collections import namedtuple
from tkinter import filedialog, messagebox, ttk

from ffmpeg_progress import Cancelled, Eta, format_seconds

BG = "#23272e"
NOTE_FONT = ("Segoe UI", 9, "italic")
VIDEO_TYPES = [("Videos", "*.mp4 *.mkv *.avi *.mov *.m4v *.ts *.flv *.wmv *.webm"), ("All files", "*.*")]
SUBTITLE_TYPES = [("Subtitles", "*.srt *.ass")]


def apply_modern_theme(root, style=None):
    """
    Apply a modern ttk theme (azure-dark if available, else clam with custom palette) to the given root window.
    Returns the ttk.Style object.
    """
    if style is None:
        style = ttk.Style(root)
    try:
        style.theme_use('azure-dark')
    except Exception:
        style.theme_use('clam')
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground="#f5f6fa", font=("Segoe UI", 11))
        style.configure('Title.TLabel', background=BG, foreground="#4fd1c5", font=("Segoe UI", 15, "bold"))
        style.configure('TButton', font=("Segoe UI", 12), padding=6, background="#353b48", foreground="#f5f6fa", borderwidth=0)
        style.map('TButton',
            background=[('active', '#4fd1c5'), ('!active', '#353b48')],
            foreground=[('active', BG), ('!active', '#f5f6fa')]
        )
        style.configure('TCheckbutton', background=BG, foreground="#f5f6fa", font=("Segoe UI", 10))
        style.configure('TRadiobutton', background=BG, foreground="#f5f6fa", font=("Segoe UI", 10))
        style.configure('TProgressbar', troughcolor=BG, background="#4fd1c5", thickness=18)
    return style


def create_styled_frame(root):
    return ttk.Frame(root, style='TFrame')


def create_styled_label(parent, text, style='TLabel', **kwargs):
    return ttk.Label(parent, text=text, style=style, background=BG, **kwargs)


def create_styled_button(parent, text, command, width=None):
    return ttk.Button(parent, text=text, command=command, width=width, style='TButton')


def app_root():
    """The hidden Tk root of the application, created on first use."""
    root = tk._default_root
    if root is None:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)  # the file dialogs, children of the root, above the other windows
        apply_modern_theme(root)
    return root


def close_app():
    """Destroy the Tk root (end of the application): the next window creates a new one."""
    root = tk._default_root
    if root is not None:
        root.destroy()


def new_window(title, size=None, topmost=True):
    """
    A window of the application, centered when its size ("WxH") is given. Dialogs stay above the other windows
    (topmost); a window open for hours (progress) only comes in front, the user can put it behind.
    Returns the Toplevel and its main frame.
    """
    win = tk.Toplevel(app_root())
    win.title(title)
    win.configure(bg=BG)
    if topmost:
        win.attributes('-topmost', True)
    else:
        win.lift()
    if size:
        width, height = (int(n) for n in size.split("x"))
        x = (win.winfo_screenwidth() - width) // 2
        y = (win.winfo_screenheight() - height) // 2
        win.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
    frame = create_styled_frame(win)
    frame.pack(fill="both", expand=True, padx=14, pady=10)
    return win, frame


def show_message(kind, title, message):
    """Show a message box ('error', 'info' or 'warning') above the other windows."""
    host = tk.Toplevel(app_root())
    host.withdraw()
    host.attributes('-topmost', True)
    try:
        getattr(messagebox, f"show{kind}")(title, message, parent=host)
    finally:
        host.destroy()


def ask_video_files(title="Choose video file(s)"):
    """File picker for one or more videos; returns the chosen paths (empty if cancelled)."""
    return filedialog.askopenfilenames(parent=app_root(), title=title, filetypes=VIDEO_TYPES)


SUBTITLE_OPTIONS = (("none", "No subtitles"), ("soft", "Softcode (attach .srt)"), ("hard", "Hardcode (burn in)"))


def ask_subtitle_option(path, allow_none=True):
    """
    Subtitle dialog for one video: no subtitles, softcoded (an added track) or hardcoded (burned in the picture),
    and the subtitle file. OK with "soft" or "hard" needs a file.
    Returns:
        (option, file) with option "none", "soft" or "hard" (file None for "none"), or None if the window is closed.
    """
    name = os.path.basename(path)
    win, frame = new_window(f"Subtitle Options for {name}")
    option = tk.StringVar(master=win, value="none" if allow_none else "soft")
    sub_file = tk.StringVar(master=win, value="")
    create_styled_label(frame, f"Subtitle options for:\n{name}").pack(pady=5)

    def toggle():
        choose_btn.state(["disabled"] if option.get() == "none" else ["!disabled"])
    for value, text in SUBTITLE_OPTIONS:
        if value != "none" or allow_none:
            ttk.Radiobutton(frame, text=text, variable=option, value=value, command=toggle,
                            style='TRadiobutton').pack(anchor="w", padx=40)

    def choose_file():
        sub_file.set(filedialog.askopenfilename(parent=win, title="Choose subtitle file", filetypes=SUBTITLE_TYPES)
                     or sub_file.get())
    choose_btn = create_styled_button(frame, "Choose Subtitle File", choose_file)
    choose_btn.pack(pady=5)
    create_styled_label(frame, "", textvariable=sub_file, wraplength=360).pack(pady=5)
    toggle()
    result = {}

    def ok():
        if option.get() != "none" and not sub_file.get():
            show_message("error", "Subtitle Error", "You selected a subtitle option but did not choose a subtitle "
                                                    "file. Please choose a subtitle file.")
            return
        result["choice"] = (option.get(), sub_file.get() or None) if option.get() != "none" else ("none", None)
        win.destroy()
    create_styled_button(frame, "OK", ok).pack(pady=10)
    win.wait_window()
    return result.get("choice")


def ask_videos_needing_subtitles(paths):
    """Check list of the videos. Returns a list of booleans (True: subtitles to add), or None if closed."""
    win, frame = new_window("Select Videos for Subtitles")
    create_styled_label(frame, "Select which videos need subtitles:").pack(pady=10)
    checks = [tk.BooleanVar(master=win, value=False) for _ in paths]
    for path, var in zip(paths, checks):
        ttk.Checkbutton(frame, text=os.path.basename(path), variable=var, style='TCheckbutton').pack(fill="x", padx=30, pady=2)
    result = {}

    def ok():
        result["needed"] = [var.get() for var in checks]
        win.destroy()
    create_styled_button(frame, "OK", ok).pack(pady=12)
    win.wait_window()
    return result.get("needed")


def ask_subtitles_for(paths):
    """
    Subtitles of each video: the subtitle dialog for a single video; for several, the check list first, then the
    dialog for each checked one. Returns a list of (option, file), or None if a window is closed.
    """
    if len(paths) == 1:
        choice = ask_subtitle_option(paths[0])
        return None if choice is None else [choice]
    needed = ask_videos_needing_subtitles(paths)
    if needed is None:
        return None
    choices = []
    for path, need in zip(paths, needed):
        choice = ask_subtitle_option(path) if need else ("none", None)
        if choice is None:
            return None
        choices.append(choice)
    return choices


ENCODER_NOTES = {
    ("H.264", False): "plays everywhere, exact size (2 passes), CPU speed",
    ("HEVC", False): "smaller files for the same quality, exact size (2 passes), slow",
    ("AV1", False): "best quality per MB, fast on recent CPUs, approximate size, needs a recent player",
    ("H.264", True): "very fast, plays everywhere, approximate size",
    ("HEVC", True): "very fast, smaller files than H.264, approximate size, most devices since ~2016",
    ("AV1", True): "very fast, best quality per MB, approximate size, recent players only",
}


def choose_encoder(title="Video encoder"):
    """
    Dialog listing the encoders that work on this computer (GPU first).
    Returns:
        encoders.Encoder or None if cancelled.
    """
    import encoders
    print("Detecting the available encoders...")
    available = encoders.available_encoders()
    if not available:
        show_message("error", "No encoder", "No working video encoder was found: is FFmpeg installed?")
        return None
    win, frame = new_window(title)
    create_styled_label(frame, "Choose the video encoder:", style='Title.TLabel').pack(anchor="w", pady=(0, 6))
    # Default: H.264 on the GPU when there is one (fast and compatible), otherwise x264
    default = next((e for e in available if e.hardware and e.codec == "H.264"), encoders.DEFAULT)
    if default not in available:
        default = available[0]
    choice = tk.StringVar(master=win, value=default.name)
    for encoder in available:
        ttk.Radiobutton(frame, text=f"{encoder.label}: {ENCODER_NOTES[(encoder.codec, bool(encoder.hardware))]}",
                        variable=choice, value=encoder.name, style='TRadiobutton').pack(anchor="w", pady=1)
    result = {}

    def ok():
        result["encoder"] = encoders.BY_NAME[choice.get()]
        win.destroy()

    create_styled_button(frame, "OK", ok, width=12).pack(pady=(10, 0))
    win.wait_window()
    return result.get("encoder")


# ---- Jobs with a progress window

JobResult = namedtuple("JobResult", "name ok detail")  # detail: what the work returned, or the error message
CANCELLED = "Cancelled."


def execute(name, work, index, report, cancel):
    """Run work(index, report, cancel) and return its JobResult: an exception becomes the error message."""
    try:
        return JobResult(name, True, work(index, report, cancel))
    except Cancelled:
        return JobResult(name, False, CANCELLED)
    except Exception as e:  # shown to the user, the other jobs go on
        print(f"❌ {name}: {e}")
        return JobResult(name, False, str(e) or type(e).__name__)


def run_jobs(title, names, work, done_text=None):
    """
    Run work(index, report, cancel) for each job, in parallel worker threads, while a window shows a bar and the
    time left for each job. The work calls report(share done, from 0 to 1) and stops (raising Cancelled) once
    cancel, a threading.Event, is set: closing the window asks whether to stop every job.
    The window closes by itself when every job is finished.
    Args:
        done_text: done_text(value returned by the work) shown on the row of a finished job; "Done" if None.
    Returns:
        list of JobResult, in the order of the names.
    """
    events = queue.Queue()  # (index, share) progress, (index, JobResult) end of a job
    cancel = threading.Event()
    results = [None] * len(names)
    win, frame = new_window(title, topmost=False)
    create_styled_label(frame, title, style='Title.TLabel').pack(anchor="w", pady=(0, 6))
    rows_parent = frame
    if len(names) > 4:
        # A scrolled list of the jobs
        canvas = tk.Canvas(frame, bg=BG, highlightthickness=0, width=460, height=330)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        rows_parent = create_styled_frame(canvas)
        canvas.create_window((0, 0), window=rows_parent, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        rows_parent.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    bars, statuses, etas = [], [], []
    for name in names:
        create_styled_label(rows_parent, name).pack(anchor="w", pady=(6, 0))
        bar = ttk.Progressbar(rows_parent, maximum=1.0, length=440, style='TProgressbar')
        bar.pack(anchor="w", pady=2)
        status = create_styled_label(rows_parent, "Waiting...", font=NOTE_FONT)
        status.pack(anchor="w")
        bars.append(bar)
        statuses.append(status)
        etas.append(Eta())

    def worker(index):
        def report(share):
            events.put((index, share))
        events.put((index, execute(names[index], work, index, report, cancel)))

    def poll():
        try:
            while True:
                index, event = events.get_nowait()
                if isinstance(event, JobResult):
                    results[index] = event
                    bars[index]["value"] = 1.0 if event.ok else bars[index]["value"]
                    if event.ok:
                        statuses[index]["text"] = "✅ " + (done_text(event.detail) if done_text else "Done")
                    else:
                        statuses[index]["text"] = "❌ " + event.detail.splitlines()[0][:120] if event.detail else "❌"
                elif results[index] is None:
                    bars[index]["value"] = event
                    left = etas[index].update(event)
                    statuses[index]["text"] = f"{int(event * 100)}% - time left: {format_seconds(left)}"
        except queue.Empty:
            pass
        if all(result is not None for result in results):
            win.after(800, win.destroy)  # the finished bars seen a moment
        else:
            win.after(200, poll)

    def on_close():
        if all(result is not None for result in results):
            win.destroy()
        elif not cancel.is_set() and messagebox.askyesno("Stop", "Stop the work in progress?", parent=win):
            cancel.set()
            for index, status in enumerate(statuses):
                if results[index] is None:
                    status["text"] = "Stopping..."
    win.protocol("WM_DELETE_WINDOW", on_close)
    for index in range(len(names)):
        threading.Thread(target=worker, args=(index,), daemon=True).start()
    poll()
    win.wait_window()
    return results


def show_results(title, results, done_text=os.path.basename):
    """
    One message at the end of the jobs: what was made (done_text of the value returned by each job) and, in an
    error message, what failed and why. Nothing when every job was cancelled.
    """
    if all(r.detail == CANCELLED for r in results if not r.ok) and not any(r.ok for r in results):
        return
    lines = [f"✔ {done_text(r.detail)}" for r in results if r.ok]
    lines += [f"✘ {r.name}:\n{r.detail}" for r in results if not r.ok]
    if any(not r.ok for r in results):
        show_message("error", f"{title} failed", "\n\n".join(lines))
    else:
        show_message("info", f"{title} finished", "\n".join(lines))
