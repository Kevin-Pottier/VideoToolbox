import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import os
import pysrt
from deep_translator import GoogleTranslator


def run_subtitle_translation():
    root = tk.Tk()
    root.title("Subtitle Translation")
    root.geometry("350x200")
    subfile_path = tk.StringVar()
    def browse():
        subfile_path.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]))
    tk.Label(root, text="Choose subtitle file to translate:").pack(pady=10)
    tk.Button(root, text="Browse Subtitles", width=20, command=browse).pack(pady=5)
    tk.Label(root, textvariable=subfile_path).pack(pady=5)
    def ok():
        if not subfile_path.get():
            messagebox.showerror("File Error", "No subtitle file selected.")
            return
        
        print(Fore.GREEN + f"Selected subtitle file for translation: {subfile_path.get()}" + Style.RESET_ALL)
        
        subs = pysrt.open(subfile_path.get(), encoding='utf-8')
        translator = GoogleTranslator(source='en', target='fr')
        total = len(subs)

        # Simple progress bar in command prompt
        for idx, sub in enumerate(subs, 1):
            try:
                sub.text = translator.translate(sub.text)
            except Exception as e:
                print(Fore.RED + f"Error translating subtitle '{sub.text}': {e}" + Style.RESET_ALL)
            # Progress bar
            progress = int(40 * idx / total)
            bar = '[' + '#' * progress + '-' * (40 - progress) + ']'
            print(f"\rTranslating: {bar} {idx}/{total}", end='', flush=True)
        print()  # Newline after progress bar

        subs.save(f"{os.path.splitext(subfile_path.get())[0]}_translated.srt", encoding='utf-8')
        print(Fore.GREEN + "Translation completed. Output saved as _translated.srt" + Style.RESET_ALL)

        root.quit()
    tk.Button(root, text="OK", command=ok).pack(pady=10)
    root.mainloop()
    root.destroy()
