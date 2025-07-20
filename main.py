
import tkinter as tk
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button

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

    apply_modern_theme(root)
    frame = create_styled_frame(root)
    frame.pack(fill="both", expand=True)
    create_styled_label(frame, "VideoCompress", style='Title.TLabel').pack(pady=(18, 2))
    create_styled_label(frame, "Choose how to use this script:").pack(pady=(0, 16))
    create_styled_button(frame, "Video Compression", lambda: set_usage("video_compression"), width=22).pack(pady=7)
    create_styled_button(frame, "Subtitle Translation", lambda: set_usage("sub_translation"), width=22).pack(pady=7)
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
        from gui_subtitle import run_subtitle_translation
        run_subtitle_translation()    

if __name__ == "__main__":
    main()