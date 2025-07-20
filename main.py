
from gui_subtitle import run_subtitle_translation
import tkinter as tk

def choose_usage_dialog():
    """
    Display a GUI window for the user to choose the main usage mode of the script.
    Returns:
        str: 'film_compression' or 'sub_translation' depending on user choice.
    """
    usage = None
    def set_usage(val):
        """
        Set the usage mode and close the window.
        Args:
            val (str): The selected usage mode.
        """
        nonlocal usage
        usage = val
        root.quit()
    root = tk.Tk()
    root.title("Choose Usage")
    root.geometry("300x200")
    root.attributes('-topmost', True)
    tk.Label(root, text="Choose how to use this script:").pack(pady=10)
    tk.Button(root, text="Video Compression", width=20, command=lambda: set_usage("video_compression")).pack(pady=5)
    tk.Button(root, text="Subtitle Translation", width=20, command=lambda: set_usage("sub_translation")).pack(pady=5)
    root.mainloop()
    root.destroy()
    return usage
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
    font_title = ("Segoe UI", 15, "bold")
    font_btn = ("Segoe UI", 12)
    font_label = ("Segoe UI", 11)
    tk.Label(root, text="VideoCompress", font=font_title, fg="#00bfff", bg="#23272e").pack(pady=(18, 2))
    tk.Label(root, text="Choose how to use this script:", font=font_label, fg="#e0e0e0", bg="#23272e").pack(pady=(0, 16))
    style = {"font": font_btn, "bg": "#2d333b", "fg": "#ffffff", "activebackground": "#00bfff", "activeforeground": "#23272e", "bd": 0, "relief": "flat"}
    tk.Button(root, text="Video Compression", width=22, command=lambda: set_usage("video_compression"), **style).pack(pady=7)
    tk.Button(root, text="Subtitle Translation", width=22, command=lambda: set_usage("sub_translation"), **style).pack(pady=7)
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