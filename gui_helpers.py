def apply_modern_theme(root, style=None):
    """
    Apply a modern ttk theme (azure-dark if available, else clam with custom palette) to the given root window.
    Returns the ttk.Style object.
    """
    from tkinter import ttk
    if style is None:
        style = ttk.Style(root)
    try:
        style.theme_use('azure-dark')
    except Exception:
        style.theme_use('clam')
        style.configure('TFrame', background="#23272e")
        style.configure('TLabel', background="#23272e", foreground="#f5f6fa", font=("Segoe UI", 11))
        style.configure('Title.TLabel', background="#23272e", foreground="#4fd1c5", font=("Segoe UI", 15, "bold"))
        style.configure('TButton', font=("Segoe UI", 12), padding=6, background="#353b48", foreground="#f5f6fa", borderwidth=0)
        style.map('TButton',
            background=[('active', '#4fd1c5'), ('!active', '#353b48')],
            foreground=[('active', '#23272e'), ('!active', '#f5f6fa')]
        )
        style.configure('TCheckbutton', background="#23272e", foreground="#f5f6fa", font=("Segoe UI", 10))
        style.configure('TRadiobutton', background="#23272e", foreground="#f5f6fa", font=("Segoe UI", 10))
        style.configure('TProgressbar', troughcolor="#23272e", background="#4fd1c5", thickness=18)
    return style

def create_styled_frame(root):
    from tkinter import ttk
    return ttk.Frame(root, style='TFrame')

def create_styled_label(parent, text, style='TLabel', **kwargs):
    from tkinter import ttk
    return ttk.Label(parent, text=text, style=style, background="#23272e", **kwargs)

def create_styled_button(parent, text, command, width=None):
    from tkinter import ttk
    return ttk.Button(parent, text=text, command=command, width=width, style='TButton')


def show_message(kind, title, message):
    """
    Show a message box ('error', 'info' or 'warning') above the other windows.
    It is attached to the open window when there is one: a second tk.Tk() would be a second
    Tcl interpreter, whose widgets and variables cannot be mixed with the first one's.
    """
    import tkinter as tk
    from tkinter import messagebox
    root = tk._default_root
    host = tk.Toplevel(root) if root is not None else tk.Tk()
    host.withdraw()
    host.attributes('-topmost', True)
    try:
        getattr(messagebox, f"show{kind}")(title, message, parent=host)
    finally:
        host.destroy()


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
    import tkinter as tk
    from tkinter import ttk
    import encoders
    print("Detecting the available encoders...")
    available = encoders.available_encoders()
    if not available:
        show_message("error", "No encoder", "No working video encoder was found: is FFmpeg installed?")
        return None
    root = tk._default_root
    win = tk.Toplevel(root) if root is not None else tk.Tk()
    win.title(title)
    win.configure(bg="#23272e")
    win.attributes('-topmost', True)
    apply_modern_theme(win)
    frame = create_styled_frame(win)
    frame.pack(fill="both", expand=True, padx=14, pady=10)
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
    if root is None:
        win.mainloop()
    else:
        win.wait_window()
    return result.get("encoder")
