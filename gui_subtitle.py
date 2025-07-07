import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import os
import pysrt
from deep_translator import GoogleTranslator
import concurrent.futures


def run_subtitle_translation():
    root = tk.Tk()
    root.title("Subtitle Translation")
    root.geometry("350x200")
    root.attributes('-topmost', True)
    subfile_path = tk.StringVar()
    def browse():
        # Always on top for file dialog
        root.lift()
        root.attributes('-topmost', True)
        subfile_path.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]))
    tk.Label(root, text="Choose subtitle file to translate:").pack(pady=10)
    tk.Button(root, text="Browse Subtitles", width=20, command=browse).pack(pady=5)
    tk.Label(root, textvariable=subfile_path).pack(pady=5)
    def ok():
        if not subfile_path.get():
            msg_root = tk.Tk()
            msg_root.attributes('-topmost', True)
            msg_root.withdraw()
            messagebox.showerror("File Error", "No subtitle file selected.", parent=msg_root)
            msg_root.destroy()
            return

        print(Fore.GREEN + f"Selected subtitle file for translation: {subfile_path.get()}" + Style.RESET_ALL)
        subs = pysrt.open(subfile_path.get(), encoding='utf-8')
        translator = GoogleTranslator(source='en', target='fr')
        total = len(subs)

        # Console progress bar setup
        import sys
        def print_progress(count, total, bar_len=40):
            filled_len = int(round(bar_len * count / float(total)))
            bar = '=' * filled_len + '-' * (bar_len - filled_len)
            percent = round(100.0 * count / float(total), 1)
            sys.stdout.write(f'\rTranslating: [{bar}] {percent}% ({count}/{total})')
            sys.stdout.flush()
            if count == total:
                print()

        results = [None] * total

        def translate_and_update(idx, text):
            try:
                translated = translator.translate(text)
            except Exception as e:
                print(Fore.RED + f"Error translating: {e}" + Style.RESET_ALL)
                translated = text
            results[idx] = translated
            print_progress(sum(r is not None for r in results), total)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(translate_and_update, idx, sub.text) for idx, sub in enumerate(subs)]
            concurrent.futures.wait(futures)

        # Assign translated text back
        for sub, translated in zip(subs, results):
            sub.text = translated

        print(Fore.GREEN + "\nTranslation completed. Output saved as _translated.srt" + Style.RESET_ALL)
        subs.save(f"{os.path.splitext(subfile_path.get())[0]}_translated.srt", encoding='utf-8')
        root.quit()
    tk.Button(root, text="OK", command=ok).pack(pady=10)
    root.mainloop()
    root.destroy()
