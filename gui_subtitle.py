
import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import os
import pysrt
from deep_translator import GoogleTranslator
import concurrent.futures
# Import reusable GUI helpers for modern, DRY window/dialog creation
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button
import threading 


def run_subtitle_translation():
    """
    Orchestrates the subtitle translation workflow:
    - Subtitle file selection
    - Language selection (source/target)
    - Runs translation with progress bar
    - Saves translated subtitle
    """

    from tkinter import ttk
    root = tk.Tk()
    root.title("Subtitle Translation")
    root.geometry("420x340")
    root.attributes('-topmost', True)
    # Apply modern theme and palette using helper
    style = ttk.Style(root)
    apply_modern_theme(root, style)
    # Override TCombobox foreground color to red for text inside dropdowns
    style.configure('TCombobox', foreground='red')
    subfile_paths = []  # List of selected subtitle files
    frame = create_styled_frame(root)
    frame.pack(fill="both", expand=True, padx=10, pady=10)


    # Language codes for FFmpeg and Google Translate
    LANGUAGES = [
        ("English", "en"), ("French", "fr"), ("German", "de"), ("Spanish", "es"), ("Italian", "it"),
        ("Portuguese", "pt"), ("Russian", "ru"), ("Chinese", "zh-cn"), ("Japanese", "ja"), ("Korean", "ko"),
        ("Arabic", "ar"), ("Dutch", "nl"), ("Greek", "el"), ("Turkish", "tr"), ("Polish", "pl"), ("Czech", "cs"),
        ("Hungarian", "hu"), ("Romanian", "ro"), ("Bulgarian", "bg"), ("Ukrainian", "uk"), ("Serbian", "sr"),
        ("Croatian", "hr"), ("Slovak", "sk"), ("Swedish", "sv"), ("Finnish", "fi"), ("Danish", "da"), ("Norwegian", "no"),
        ("Hebrew", "he"), ("Hindi", "hi"), ("Vietnamese", "vi"), ("Indonesian", "id"), ("Malay", "ms"), ("Thai", "th"),
        ("Filipino", "tl"), ("Persian", "fa"), ("Urdu", "ur"), ("Bengali", "bn"), ("Slovenian", "sl"), ("Estonian", "et"),
        ("Latvian", "lv"), ("Lithuanian", "lt"), ("Georgian", "ka"), ("Armenian", "hy"), ("Azerbaijani", "az"),
        ("Albanian", "sq"), ("Macedonian", "mk"), ("Basque", "eu"), ("Catalan", "ca"), ("Galician", "gl"), ("Welsh", "cy"),
        ("Irish", "ga"), ("Scottish Gaelic", "gd"), ("Icelandic", "is"), ("Maltese", "mt"), ("Swahili", "sw"),
        ("Afrikaans", "af"), ("Zulu", "zu"), ("Xhosa", "xh"), ("Sesotho", "st"), ("Yoruba", "yo"), ("Igbo", "ig"),
        ("Hausa", "ha"), ("Somali", "so"), ("Amharic", "am"), ("Tigrinya", "ti"), ("Oromo", "om"), ("Kinyarwanda", "rw"),
        ("Kirundi", "rn"), ("Lingala", "ln"), ("Luganda", "lg"), ("Shona", "sn"), ("Sesotho sa Leboa", "nso"),
        ("Tswana", "tn"), ("Tsonga", "ts"), ("Venda", "ve"), ("Xitsonga", "xh")
    ]

    src_lang = tk.StringVar(value="en")
    tgt_lang = tk.StringVar(value="fr")




    def browse():
        root.lift()
        root.attributes('-topmost', True)
        files = filedialog.askopenfilenames(title="Choose subtitle file(s)", filetypes=[("Subtitles", "*.srt *.ass")])
        if files:
            subfile_paths.clear()
            subfile_paths.extend(root.tk.splitlist(files))
            subfile_label.config(text="\n".join([os.path.basename(f) for f in subfile_paths]))


    create_styled_label(frame, text="Subtitle Translation", style='Title.TLabel').pack(pady=(0, 8))
    create_styled_label(frame, text="Choose subtitle file(s) to translate:").pack(pady=(0, 6))
    browse_frame = create_styled_frame(frame)
    browse_frame.pack(pady=(0, 4))
    from main import create_styled_button  # Import here to avoid circular import issues
    create_styled_button(browse_frame, text="Browse Subtitles", width=18, command=browse).pack(side="left", padx=(0, 8))
    subfile_label = create_styled_label(browse_frame, "", width=32, anchor="w", justify="left")
    subfile_label.pack(side="left")

    # Language selection dropdowns (aesthetic and practical)

    lang_frame = create_styled_frame(frame)
    lang_frame.pack(pady=12)
    create_styled_label(lang_frame, text="From:").grid(row=0, column=0, padx=5)
    src_combo = ttk.Combobox(lang_frame, textvariable=src_lang, width=18, state="readonly", style='TCombobox')
    src_combo['values'] = [f"{name} ({code})" for name, code in LANGUAGES]
    src_combo.current([code for name, code in LANGUAGES].index(src_lang.get()))
    src_combo.grid(row=0, column=1, padx=5)
    create_styled_label(lang_frame, text="To:").grid(row=0, column=2, padx=5)
    tgt_combo = ttk.Combobox(lang_frame, textvariable=tgt_lang, width=18, state="readonly", style='TCombobox')
    tgt_combo['values'] = [f"{name} ({code})" for name, code in LANGUAGES]
    tgt_combo.current([code for name, code in LANGUAGES].index(tgt_lang.get()))
    tgt_combo.grid(row=0, column=3, padx=5)

    # Update language code on selection
    def update_src(event):
        # Always set only the language code, not the display string
        idx = src_combo.current()
        src_lang.set(LANGUAGES[idx][1])
    def update_tgt(event):
        idx = tgt_combo.current()
        tgt_lang.set(LANGUAGES[idx][1])
    src_combo.bind("<<ComboboxSelected>>", update_src)
    tgt_combo.bind("<<ComboboxSelected>>", update_tgt)

    # --- Batch progress window for multiple files ---
    # These will be reset for each batch
    progress_bars = []
    status_labels = []

    def start_translation():
        if not subfile_paths:
            msg_root = tk.Tk()
            msg_root.attributes('-topmost', True)
            msg_root.withdraw()
            messagebox.showerror("File Error", "No subtitle file(s) selected.", parent=msg_root)
            msg_root.destroy()
            return
        ok_btn.config(state="disabled")
        # If only one file, use current window for progress
        if len(subfile_paths) == 1:
            show_single_progress(subfile_paths[0])
        else:
            show_batch_progress()

    ok_btn = create_styled_button(frame, text="OK", command=start_translation)
    ok_btn.pack(pady=16)

    def show_single_progress(subfile):

        # Remove old widgets
        for widget in frame.winfo_children():
            if widget not in [ok_btn, browse_frame, lang_frame]:
                widget.destroy()
        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=100, length=320, style='TProgressbar')
        progress_bar.pack(pady=(10, 0))
        status_label = create_styled_label(frame, "", style='TLabel', font=("Segoe UI", 10, "italic"))
        status_label.pack(pady=(4, 0))
        def on_done():
            messagebox.showinfo("Translation Complete", f"Translation completed!\nOutput saved as:\n{os.path.splitext(subfile)[0]}_translated.srt")
            root.destroy()
        threading.Thread(target=translate_file, args=(subfile, progress_var, status_label, on_done), daemon=True).start()

    def show_batch_progress():
        # New window for batch progress
        nonlocal progress_bars, status_labels
        progress_bars = []
        status_labels = []
        batch_win = tk.Toplevel(root)
        batch_win.title("Batch Subtitle Translation Progress")
        batch_win.geometry("500x{}".format(120 + 60 * len(subfile_paths)))
        batch_win.configure(bg="#23272e")
        apply_modern_theme(batch_win)
        batch_frame = create_styled_frame(batch_win)
        batch_frame.pack(fill="both", expand=True, padx=10, pady=10)
        create_styled_label(batch_frame, text="Batch Subtitle Translation Progress", style='Title.TLabel').pack(pady=(0, 8))
        for i, subfile in enumerate(subfile_paths):
            file_label = create_styled_label(batch_frame, text=os.path.basename(subfile), anchor="w")
            file_label.pack(anchor="w")
            pvar = tk.DoubleVar(value=0)
            pbar = ttk.Progressbar(batch_frame, variable=pvar, maximum=100, length=420, style='TProgressbar')
            pbar.pack(pady=(0, 2))
            slabel = create_styled_label(batch_frame, text="Waiting...", style='TLabel', font=("Segoe UI", 9, "italic"))
            slabel.pack(anchor="w", pady=(0, 8))
            progress_bars.append((pvar, pbar))
            status_labels.append(slabel)
        # Start all translations in parallel (1 thread per file)
        def on_file_done(idx, subfile):
            def finish():
                status_labels[idx].config(text="Done!")
                messagebox.showinfo("Translation Complete", f"Translation completed!\nOutput saved as:\n{os.path.splitext(subfile)[0]}_translated.srt")
                # If all done, close window
                if all(status_labels[i].cget("text") == "Done!" for i in range(len(subfile_paths))):
                    batch_win.destroy()
                    root.destroy()
            root.after(0, finish)
        for idx, subfile in enumerate(subfile_paths):
            threading.Thread(target=translate_file, args=(subfile, progress_bars[idx][0], status_labels[idx], lambda idx=idx, subfile=subfile: on_file_done(idx, subfile)), daemon=True).start()

    def translate_file(subfile, progress_var, status_label, on_done):
        # Always use only the language code for GoogleTranslator
        source = src_lang.get()
        target = tgt_lang.get()
        # Defensive: if value is like 'English (en)', extract code
        if '(' in source and ')' in source:
            source = source.split('(')[-1].split(')')[0].strip()
        if '(' in target and ')' in target:
            target = target.split('(')[-1].split(')')[0].strip()
        print(Fore.GREEN + f"Selected subtitle file for translation: {subfile}" + Style.RESET_ALL)
        print(Fore.YELLOW + f"Translating from {source} to {target}" + Style.RESET_ALL)
        subs = pysrt.open(subfile, encoding='utf-8')
        translator = GoogleTranslator(source=source, target=target)
        total = len(subs)
        results = [None] * total
        import time, concurrent.futures
        completed = [0]
        start_time = time.time()
        def update_progress(count):
            percent = int(100.0 * count / float(total))
            progress_var.set(percent)
            status_label.config(text=f"Translating... {percent}% ({count}/{total})")
        def translate_and_update(idx, text):
            try:
                translated = translator.translate(text)
            except Exception as e:
                print(Fore.RED + f"Error translating: {e}" + Style.RESET_ALL)
                translated = text
            results[idx] = translated
            def update():
                completed[0] += 1
                update_progress(completed[0])
                # Print ETA in terminal
                elapsed = time.time() - start_time
                if completed[0] > 0 and completed[0] < total:
                    eta = elapsed / completed[0] * (total - completed[0])
                    mins, secs = divmod(int(eta), 60)
                    print(f"[{os.path.basename(subfile)}] {completed[0]}/{total} - ETA: {mins:02d}:{secs:02d}", end='\r')
                elif completed[0] == total:
                    print(f"[{os.path.basename(subfile)}] 100% - Done!{' '*20}")
            root.after(0, update)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(translate_and_update, idx, sub.text) for idx, sub in enumerate(subs)]
            concurrent.futures.wait(futures)
        for sub, translated in zip(subs, results):
            sub.text = translated
        subs.save(f"{os.path.splitext(subfile)[0]}_translated.srt", encoding='utf-8')
        root.after(0, on_done)

    root.mainloop()
    root.destroy()
