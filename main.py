
from gui_subtitle import run_subtitle_translation
import tkinter as tk

def choose_usage_dialog():
    """
    Display a GUI window for the user to choose the main usage mode of the script.
    Returns:
        str: 'film_compression' or 'sub_translation' depending on user choice.
    """
    from tkinter import ttk
    usage = None
    def set_usage(val):
        nonlocal usage
        usage = val
        root.quit()
    root = tk.Tk()
    root.title("VideoCompress - Main Menu")
    root.geometry("380x220")
    root.configure(bg="#23272e")
    root.attributes('-topmost', True)
    # Center window
    root.update_idletasks()
    w = 380
    h = 220
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ttk style
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TFrame', background="#23272e")
    style.configure('TLabel', background="#23272e", foreground="#e0e0e0", font=("Segoe UI", 11))
    style.configure('Title.TLabel', background="#23272e", foreground="#00bfff", font=("Segoe UI", 15, "bold"))
    style.configure('TButton', font=("Segoe UI", 12), padding=6, background="#2d333b", foreground="#ffffff")
    style.map('TButton', background=[('active', '#00bfff')], foreground=[('active', '#23272e')])

    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="VideoCompress", style='Title.TLabel').pack(pady=(18, 2))
    ttk.Label(frame, text="Choose how to use this script:").pack(pady=(0, 16))
    ttk.Button(frame, text="Video Compression", width=22, command=lambda: set_usage("video_compression")).pack(pady=7)
    ttk.Button(frame, text="Subtitle Translation", width=22, command=lambda: set_usage("sub_translation")).pack(pady=7)
    root.mainloop()
    root.destroy()
    return usage

def main():
    """
    Main entry point for the script. Runs the selected workflow based on user choice.
    """
    usage = choose_usage_dialog()
    if usage == "video_compression":
        from gui_film import run_video_compression
        run_video_compression()
    elif usage == "sub_translation":
        run_subtitle_translation()

if __name__ == "__main__":
    main()