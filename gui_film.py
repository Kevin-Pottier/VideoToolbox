import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from colorama import Fore, Style
import os
from compression import run_compression

def run_film_compression():
    # Step 1: Select video file
    file_path = None
    while not file_path:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        file_path = filedialog.askopenfilename(title="Choose a video file", filetypes=[("Videos", "*.mp4 *.mkv *.avi")])
        root.destroy()
        if not file_path:
            msg_root = tk.Tk()
            msg_root.attributes('-topmost', True)
            msg_root.withdraw()
            messagebox.showerror("File Error", "No video file selected. Please choose a video file.", parent=msg_root)
            msg_root.destroy()

    # Step 2: Subtitle options
    sub_option = None
    sub_file = None
    while sub_option is None or (sub_option in ("soft", "hard") and not sub_file):
        sub_root = tk.Tk()
        sub_root.attributes('-topmost', True)
        sub_option_var = tk.StringVar(value="none")
        sub_file_var = tk.StringVar(value="")
        sub_root.title("Subtitle Options")
        sub_root.geometry("350x220")
        tk.Label(sub_root, text="Subtitle options:").pack(pady=5)
        def toggle_sub():
            if sub_option_var.get() == "none":
                sub_btn.config(state="disabled")
                sub_file_var.set("")
            else:
                sub_btn.config(state="normal")
        tk.Radiobutton(sub_root, text="No subtitles", variable=sub_option_var, value="none", command=toggle_sub).pack(anchor="w", padx=40)
        tk.Radiobutton(sub_root, text="Softcode (attach .srt)", variable=sub_option_var, value="soft", command=toggle_sub).pack(anchor="w", padx=40)
        tk.Radiobutton(sub_root, text="Hardcode (burn in)", variable=sub_option_var, value="hard", command=toggle_sub).pack(anchor="w", padx=40)
        sub_btn = tk.Button(sub_root, text="Choose Subtitle File", state="disabled", command=lambda: sub_file_var.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]) or sub_file_var.get()))
        sub_btn.pack(pady=5)
        sub_label = tk.Label(sub_root, textvariable=sub_file_var)
        sub_label.pack(pady=5)
        def ok():
            sub_root.quit()
        tk.Button(sub_root, text="OK", command=ok).pack(pady=10)
        sub_root.after(100, toggle_sub)
        sub_root.mainloop()
        sub_option = sub_option_var.get()
        sub_file = sub_file_var.get() if sub_file_var.get() else None
        sub_root.destroy()
        if sub_option in ("soft", "hard") and not sub_file:
            msg_root = tk.Tk()
            msg_root.attributes('-topmost', True)
            msg_root.withdraw()
            messagebox.showerror("Subtitle Error", "You selected a subtitle option but did not choose a subtitle file. Please choose a subtitle file.", parent=msg_root)
            msg_root.destroy()

    # Step 3: Output container
    container_root = tk.Tk()
    container_root.withdraw()
    container_root.attributes('-topmost', True)
    container_choice = tk.StringVar(value="mp4")
    def set_choice(val):
        container_choice.set(val)
        container_root.quit()
    container_win = tk.Toplevel(container_root)
    container_win.title("Choose Output Container")
    container_win.geometry("300x150")
    container_win.attributes('-topmost', True)
    tk.Label(container_win, text="Choose the output container:").pack(pady=10)
    tk.Button(container_win, text="MP4", width=15, command=lambda: set_choice("mp4")).pack(pady=5)
    tk.Button(container_win, text="MKV", width=15, command=lambda: set_choice("mkv")).pack(pady=5)
    container_win.protocol("WM_DELETE_WINDOW", container_root.quit)
    container_root.mainloop()
    ext = container_choice.get()
    container_root.destroy()
    if ext not in ("mp4", "mkv"):
        print(Fore.RED + "No container selected. Aborting." + Style.RESET_ALL)
        return

    # Step 4: Max size
    max_size_gb = None
    while max_size_gb is None or max_size_gb <= 0:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            max_size_gb = float(simpledialog.askstring("Target Video Size", "Enter the maximum file size in GB:", parent=root))
        except Exception:
            max_size_gb = None
        root.destroy()
        if not max_size_gb or max_size_gb <= 0:
            msg_root = tk.Tk()
            msg_root.attributes('-topmost', True)
            msg_root.withdraw()
            messagebox.showerror("Size Error", "Invalid size. Must be greater than 0.", parent=msg_root)
            msg_root.destroy()

    # Step 5: Run compression logic
    run_compression(file_path, sub_option, sub_file, ext, max_size_gb)
