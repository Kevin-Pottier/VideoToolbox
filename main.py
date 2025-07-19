
from gui_film import run_film_compression
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
    tk.Button(root, text="Film Compression", width=20, command=lambda: set_usage("film_compression")).pack(pady=5)
    tk.Button(root, text="Subtitle Translation", width=20, command=lambda: set_usage("sub_translation")).pack(pady=5)
    root.mainloop()
    root.destroy()
    return usage

def main():
    """
    Main entry point for the script. Runs the selected workflow based on user choice.
    """
    usage = choose_usage_dialog()
    if usage == "film_compression":
        run_film_compression()
    elif usage == "sub_translation":
        run_subtitle_translation()

if __name__ == "__main__":
    main()