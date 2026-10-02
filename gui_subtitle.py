
import concurrent.futures
import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import os
import time
import pysrt
from deep_translator import GoogleTranslator
import deepl
# Import reusable GUI helpers for modern, DRY window/dialog creation
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button, show_message
from utils import read_subtitle_text
import threading 


# Languages offered for translation, with the codes GoogleTranslator (deep-translator) accepts
LANGUAGES = [
    ("English", "en"), ("French", "fr"), ("German", "de"), ("Spanish", "es"), ("Italian", "it"),
    ("Portuguese", "pt"), ("Russian", "ru"), ("Chinese", "zh-CN"), ("Japanese", "ja"), ("Korean", "ko"),
    ("Arabic", "ar"), ("Dutch", "nl"), ("Greek", "el"), ("Turkish", "tr"), ("Polish", "pl"), ("Czech", "cs"),
    ("Hungarian", "hu"), ("Romanian", "ro"), ("Bulgarian", "bg"), ("Ukrainian", "uk"), ("Serbian", "sr"),
    ("Croatian", "hr"), ("Slovak", "sk"), ("Swedish", "sv"), ("Finnish", "fi"), ("Danish", "da"), ("Norwegian", "no"),
    ("Hebrew", "iw"), ("Hindi", "hi"), ("Vietnamese", "vi"), ("Indonesian", "id"), ("Malay", "ms"), ("Thai", "th"),
    ("Filipino", "tl"), ("Persian", "fa"), ("Urdu", "ur"), ("Bengali", "bn"), ("Slovenian", "sl"), ("Estonian", "et"),
    ("Latvian", "lv"), ("Lithuanian", "lt"), ("Georgian", "ka"), ("Armenian", "hy"), ("Azerbaijani", "az"),
    ("Albanian", "sq"), ("Macedonian", "mk"), ("Basque", "eu"), ("Catalan", "ca"), ("Galician", "gl"), ("Welsh", "cy"),
    ("Irish", "ga"), ("Scottish Gaelic", "gd"), ("Icelandic", "is"), ("Maltese", "mt"), ("Swahili", "sw"),
    ("Afrikaans", "af"), ("Zulu", "zu"), ("Xhosa", "xh"), ("Sesotho", "st"), ("Yoruba", "yo"), ("Igbo", "ig"),
    ("Hausa", "ha"), ("Somali", "so"), ("Amharic", "am"), ("Tigrinya", "ti"), ("Oromo", "om"), ("Kinyarwanda", "rw"),
    ("Lingala", "ln"), ("Luganda", "lg"), ("Shona", "sn"), ("Sesotho sa Leboa", "nso"),
    ("Tsonga", "ts")
]

TRANSLATION_WORKERS = 4  # parallel requests: more makes Google limit (or block) the requests sooner
TRANSLATION_ATTEMPTS = 4  # per text, with a delay doubling between attempts (1 s, 2 s, 4 s)
RETRY_BASE_DELAY = 1.0
MAX_CONSECUTIVE_FAILURES = 10  # texts failing in a row: Google is limiting or blocking the requests


class TranslationBlocked(RuntimeError):
    pass


def translate_with_retry(translate, text, attempts=TRANSLATION_ATTEMPTS, base_delay=RETRY_BASE_DELAY, sleep=time.sleep):
    """translate(text), retried with an exponential backoff; the last error is raised if every attempt fails."""
    if not text.strip():
        return text  # nothing to translate (the translator rejects empty texts)
    for attempt in range(attempts):
        try:
            return translate(text)
        except Exception:
            if attempt == attempts - 1:
                raise
            sleep(base_delay * 2 ** attempt)


def translate_lines(lines, make_translator, on_progress=None, workers=TRANSLATION_WORKERS,
                    max_consecutive_failures=MAX_CONSECUTIVE_FAILURES, **retry_options):
    """
    Translate subtitle texts in parallel.
    - make_translator() creates a translator (an object with translate(text)). Each worker thread gets
      its own: deep-translator's GoogleTranslator stores the text of the request in the instance, so a
      shared one can send the text of another thread and give a line the translation of another one.
    - identical texts ("Yes.", "Thank you."...) are translated once
    - on_progress(number of lines done) is called from the worker threads
    Returns:
        tuple: (translated lines, number of lines kept as they were because their translation failed)
    Raises:
        TranslationBlocked: when max_consecutive_failures texts fail in a row
    """
    positions = {}
    for index, text in enumerate(lines):
        positions.setdefault(text, []).append(index)
    translations = {}
    failed = []
    lock = threading.Lock()
    consecutive_failures = [0]
    blocked = threading.Event()
    local = threading.local()

    def translate_one(text):
        if blocked.is_set():
            return
        if not hasattr(local, "translator"):
            local.translator = make_translator()
        try:
            translations[text] = translate_with_retry(local.translator.translate, text, **retry_options)
            with lock:
                consecutive_failures[0] = 0
        except Exception as e:
            print(Fore.RED + f"Error translating {text!r}: {e}" + Style.RESET_ALL)
            translations[text] = text
            with lock:
                failed.append(text)
                consecutive_failures[0] += 1
                if consecutive_failures[0] >= max_consecutive_failures:
                    blocked.set()
        if on_progress:
            on_progress(len(positions[text]))

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(translate_one, positions))
    if blocked.is_set():
        raise TranslationBlocked(f"Google Translate stopped answering ({max_consecutive_failures} failures in a row): "
                                 "it may be limiting or blocking the requests. Try again later.")
    return [translations[text] for text in lines], sum(len(positions[text]) for text in failed)


def translate_texts(lines, source, target, deepl_key=None, on_progress=None, make_google=None):
    """
    Translate subtitle texts with DeepL when a key is given, Google finishing the lines DeepL could not
    translate (quota used up, key refused, DeepL unreachable...), else with Google.
    Returns:
        tuple: (translated lines, number of lines kept untranslated, note for the user, "" when none)
    Raises:
        TranslationBlocked: when Google keeps refusing the requests
    """
    make_google = make_google or (lambda: GoogleTranslator(source=source, target=target))
    if not deepl_key:
        translated, failed = translate_lines(lines, make_google, on_progress=on_progress)
        return translated, failed, ""
    try:
        return deepl.translate_lines(lines, deepl_key, source, target, on_progress=on_progress), 0, ""
    except deepl.DeepLError as e:
        print(Fore.YELLOW + f"{e} The other lines are translated with Google." + Style.RESET_ALL)
        done = e.done
        remaining = [line for line in lines if line not in done]
        translated, failed = translate_lines(remaining, make_google, on_progress=on_progress)
        done.update(zip(remaining, translated))
        note = f"\n\nDeepL stopped: {e}\n{len(remaining)} line(s) were translated with Google."
        return [done[line] for line in lines], failed, note


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
    root.attributes('-topmost', True)
    # Apply modern theme and palette using helper
    style = ttk.Style(root)
    apply_modern_theme(root, style)
    # Override TCombobox foreground color to red for text inside dropdowns
    style.configure('TCombobox', foreground='red')
    from typing import List
    subfile_paths: List[str] = []  # List of selected subtitle files
    frame = create_styled_frame(root)
    frame.pack(fill="both", expand=True, padx=10, pady=10)



    src_lang = tk.StringVar(value="en", master=root)
    tgt_lang = tk.StringVar(value="fr", master=root)




    def browse():
        root.lift()
        root.attributes('-topmost', True)
        files = filedialog.askopenfilenames(title="Choose subtitle file(s)", filetypes=[("SubRip subtitles", "*.srt")])
        if files:
            subfile_paths.clear()
            subfile_paths.extend(root.tk.splitlist(files))
            subfile_label.config(text="\n".join([os.path.basename(f) for f in subfile_paths]))


    create_styled_label(frame, text="Subtitle Translation", style='Title.TLabel').pack(pady=(0, 8))
    create_styled_label(frame, text="Choose subtitle file(s) to translate:").pack(pady=(0, 6))
    browse_frame = create_styled_frame(frame)
    browse_frame.pack(pady=(0, 4))
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

    # Translation service: DeepL (official API, free key) or Google (no key, but it may refuse the requests)
    saved_key = deepl.load_key()
    engine = tk.StringVar(master=root, value="deepl" if saved_key else "google")
    key_var = tk.StringVar(master=root, value=saved_key)
    remember_key = tk.BooleanVar(master=root, value=True)
    engine_frame = create_styled_frame(frame)
    engine_frame.pack(fill="x", pady=(0, 4))
    create_styled_label(engine_frame, text="Translation service:").pack(anchor="w")
    ttk.Radiobutton(engine_frame, text="Google Translate: no key, but it may refuse many requests", variable=engine,
                    value="google", style='TRadiobutton').pack(anchor="w", padx=10)
    ttk.Radiobutton(engine_frame, text="DeepL: better translations, free key (500,000 characters a month)",
                    variable=engine, value="deepl", style='TRadiobutton').pack(anchor="w", padx=10)
    key_row = create_styled_frame(engine_frame)
    key_row.pack(anchor="w", padx=30, pady=(2, 0))
    create_styled_label(key_row, text="DeepL key:").pack(side="left")
    ttk.Entry(key_row, textvariable=key_var, width=40, show="•").pack(side="left", padx=6)
    ttk.Checkbutton(engine_frame, text="Remember the key on this computer", variable=remember_key,
                    style='TCheckbutton').pack(anchor="w", padx=30)
    create_styled_label(engine_frame, text="Free key: www.deepl.com/pro-api (DeepL API Free). If DeepL stops, "
                                           "Google translates the rest.", font=("Segoe UI", 9, "italic")).pack(
        anchor="w", padx=30)

    # --- Batch progress window for multiple files ---
    # These will be reset for each batch
    progress_bars = []
    status_labels = []
    # Read in the Tk thread when the translation starts, used by the worker threads
    options = {}

    def start_translation():
        if not subfile_paths:
            show_message("error", "File Error", "No subtitle file(s) selected.")
            return
        key = key_var.get().strip() if engine.get() == "deepl" else ""
        if engine.get() == "deepl" and not key:
            show_message("error", "DeepL key", "Enter your DeepL key (free on www.deepl.com/pro-api), or choose Google.")
            return
        if key and remember_key.get():
            deepl.save_key(key)
        # Only the language code, not the display string ('English (en)')
        options.update(source=src_lang.get().split('(')[-1].rstrip(')').strip(),
                       target=tgt_lang.get().split('(')[-1].rstrip(')').strip(), key=key)
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
            if widget not in [ok_btn, browse_frame, lang_frame, engine_frame]:
                widget.destroy()
        progress_var = tk.DoubleVar(value=0, master=root)
        progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=100, length=320, style='TProgressbar')
        progress_bar.pack(pady=(10, 0))
        status_label = create_styled_label(frame, "", style='TLabel', font=("Segoe UI", 10, "italic"))
        status_label.pack(pady=(4, 0))
        def on_done(report):
            messagebox.showinfo("Translation Complete", f"Translation completed!\nOutput saved as:\n{os.path.splitext(subfile)[0]}_translated.srt{report}")
            root.destroy()
        def on_error(message):
            status_label.config(text="Error")
            messagebox.showerror("Translation Error", f"{os.path.basename(subfile)}:\n{message}")
            ok_btn.config(state="normal")
        threading.Thread(target=translate_file, args=(subfile, progress_var, status_label, on_done, on_error), daemon=True).start()

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
            pvar = tk.DoubleVar(value=0, master=batch_win)
            pbar = ttk.Progressbar(batch_frame, variable=pvar, maximum=100, length=420, style='TProgressbar')
            pbar.pack(pady=(0, 2))
            slabel = create_styled_label(batch_frame, text="Waiting...", style='TLabel', font=("Segoe UI", 9, "italic"))
            slabel.pack(anchor="w", pady=(0, 8))
            progress_bars.append((pvar, pbar))
            status_labels.append(slabel)
        # Start all translations in parallel (1 thread per file)
        def close_if_all_finished():
            if all(status_labels[i].cget("text") == "Done!" or status_labels[i].cget("text").startswith("Error")
                   for i in range(len(subfile_paths))):
                batch_win.destroy()
                root.destroy()
        def on_file_done(idx, subfile, report):
            status_labels[idx].config(text="Done!")
            messagebox.showinfo("Translation Complete", f"Translation completed!\nOutput saved as:\n{os.path.splitext(subfile)[0]}_translated.srt{report}")
            close_if_all_finished()
        def on_file_error(idx, subfile, message):
            status_labels[idx].config(text=f"Error: {message.splitlines()[0]}")
            messagebox.showerror("Translation Error", f"{os.path.basename(subfile)}:\n{message}")
            close_if_all_finished()
        for idx, subfile in enumerate(subfile_paths):
            threading.Thread(target=translate_file, args=(
                subfile, progress_bars[idx][0], status_labels[idx],
                lambda report, idx=idx, subfile=subfile: on_file_done(idx, subfile, report),
                lambda message, idx=idx, subfile=subfile: on_file_error(idx, subfile, message)
            ), daemon=True).start()

    def failed_note(failed):
        if not failed:
            return ""
        return f"\n\n⚠ {failed} line(s) could not be translated and were kept as is (see console)."

    def translate_file(subfile, progress_var, status_label, on_done, on_error):
        """
        Translate one subtitle file in a worker thread. Tk is only touched through root.after:
        on_done(report for the user) or on_error(message) is called at the end.
        """
        try:
            failed, note = translate_subtitles(subfile, progress_var, status_label)
        except Exception as e:  # a dead thread would leave the progress window stuck
            print(Fore.RED + f"Translation of {subfile} failed: {e}" + Style.RESET_ALL)
            root.after(0, on_error, str(e) or type(e).__name__)
            return
        root.after(0, on_done, failed_note(failed) + note)

    def translate_subtitles(subfile, progress_var, status_label):
        """Translate one file (worker thread). Returns (lines kept untranslated, note for the user)."""
        source, target, key = options["source"], options["target"], options["key"]
        print(Fore.GREEN + f"Selected subtitle file for translation: {subfile}" + Style.RESET_ALL)
        print(Fore.YELLOW + f"Translating from {source} to {target} with {'DeepL' if key else 'Google'}" + Style.RESET_ALL)
        text, encoding = read_subtitle_text(subfile)
        if encoding != "utf-8-sig":
            print(Fore.YELLOW + f"{os.path.basename(subfile)} is not UTF-8, read as {encoding}" + Style.RESET_ALL)
        subs = pysrt.from_string(text)
        if not subs:
            raise ValueError("No subtitle found: is it a valid SubRip (.srt) file?")
        if not key:
            GoogleTranslator(source=source, target=target)  # reports an unsupported language before starting
        total = len(subs)
        completed = [0]
        start_time = time.time()
        def update(count):
            # Runs in the Tk thread (scheduled with root.after)
            completed[0] += count
            percent = int(100.0 * completed[0] / total)
            progress_var.set(percent)
            status_label.config(text=f"Translating... {percent}% ({completed[0]}/{total})")
            elapsed = time.time() - start_time
            if completed[0] < total:
                mins, secs = divmod(int(elapsed / completed[0] * (total - completed[0])), 60)
                print(f"[{os.path.basename(subfile)}] {completed[0]}/{total} - ETA: {mins:02d}:{secs:02d}", end='\r')
            else:
                print(f"[{os.path.basename(subfile)}] 100% - Done!{' '*20}")
        translated, failed, note = translate_texts([sub.text for sub in subs], source, target, key,
                                                   on_progress=lambda count: root.after(0, update, count))
        for sub, new_text in zip(subs, translated):
            sub.text = new_text
        subs.save(f"{os.path.splitext(subfile)[0]}_translated.srt", encoding='utf-8')
        return failed, note

    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass  # already destroyed once the translation is complete
