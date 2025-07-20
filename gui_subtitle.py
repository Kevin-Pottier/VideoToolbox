
import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import os
import pysrt
from deep_translator import GoogleTranslator
import concurrent.futures
# Import reusable GUI helpers for modern, DRY window/dialog creation
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button


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
    subfile_path = tk.StringVar()
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
        subfile_path.set(filedialog.askopenfilename(title="Choose subtitle file", filetypes=[("Subtitles", "*.srt *.ass")]))

    create_styled_label(frame, text="Subtitle Translation", style='Title.TLabel').pack(pady=(0, 8))
    create_styled_label(frame, text="Choose subtitle file to translate:").pack(pady=(0, 6))
    browse_frame = create_styled_frame(frame)
    browse_frame.pack(pady=(0, 4))
    from main import create_styled_button  # Import here to avoid circular import issues
    create_styled_button(browse_frame, text="Browse Subtitles", width=18, command=browse).pack(side="left", padx=(0, 8))
    create_styled_label(browse_frame, "", textvariable=subfile_path, width=32, anchor="w").pack(side="left")

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
        """
        Update the source language code when the user selects a new language.
        """
        idx = src_combo.current()
        src_lang.set(LANGUAGES[idx][1])
    def update_tgt(event):
        """
        Update the target language code when the user selects a new language.
        """
        idx = tgt_combo.current()
        tgt_lang.set(LANGUAGES[idx][1])
    src_combo.bind("<<ComboboxSelected>>", update_src)
    tgt_combo.bind("<<ComboboxSelected>>", update_tgt)

    # --- Progress bar and status label ---
    progress_var = tk.DoubleVar(value=0)
    progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=100, length=320, style='TProgressbar')
    progress_bar.pack(pady=(10, 0))
    status_label = create_styled_label(frame, "", style='TLabel', font=("Segoe UI", 10, "italic"))
    status_label.pack(pady=(4, 0))

    # --- OK button (will be disabled during translation) ---
    ok_btn = create_styled_button(frame, text="OK", command=lambda: start_translation())
    ok_btn.pack(pady=16)

    def start_translation():
        if not subfile_path.get():
            msg_root = tk.Tk()
            msg_root.attributes('-topmost', True)
            msg_root.withdraw()
            messagebox.showerror("File Error", "No subtitle file selected.", parent=msg_root)
            msg_root.destroy()
            return
        ok_btn.config(state="disabled")
        progress_var.set(0)
        status_label.config(text="Starting translation...")
        root.update_idletasks()
        import threading
        threading.Thread(target=translate_subtitles, daemon=True).start()

    def translate_subtitles():
        source = src_lang.get()
        target = tgt_lang.get()
        print(Fore.GREEN + f"Selected subtitle file for translation: {subfile_path.get()}" + Style.RESET_ALL)
        print(Fore.YELLOW + f"Translating from {source} to {target}" + Style.RESET_ALL)
        subs = pysrt.open(subfile_path.get(), encoding='utf-8')
        translator = GoogleTranslator(source=source, target=target)
        total = len(subs)
        results = [None] * total

        def update_progress(count):
            percent = int(100.0 * count / float(total))
            progress_var.set(percent)
            status_label.config(text=f"Translating... {percent}% ({count}/{total})")
            root.update_idletasks()


        import threading
        completed = [0]  # mutable counter for progress

        def translate_and_update(idx, text):
            try:
                translated = translator.translate(text)
            except Exception as e:
                print(Fore.RED + f"Error translating: {e}" + Style.RESET_ALL)
                translated = text
            results[idx] = translated
            # Thread-safe progress update
            def update():
                completed[0] += 1
                update_progress(completed[0])
            root.after(0, update)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(translate_and_update, idx, sub.text) for idx, sub in enumerate(subs)]
            concurrent.futures.wait(futures)

        # Assign translated text back
        for sub, translated in zip(subs, results):
            sub.text = translated

        print(Fore.GREEN + "\nTranslation completed. Output saved as _translated.srt" + Style.RESET_ALL)
        subs.save(f"{os.path.splitext(subfile_path.get())[0]}_translated.srt", encoding='utf-8')
        def finish():
            status_label.config(text="Translation completed! Output saved.")
            ok_btn.config(state="normal")
        root.after(0, finish)

    root.mainloop()
    root.destroy()
