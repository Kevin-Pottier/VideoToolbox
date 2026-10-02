"""
Play one scenario of the end-to-end battery through the real windows, from the main menu:
    python tests/e2e/drive.py scenario.json        (run.py writes the scenario and runs this script)

Every Tk event loop (mainloop or wait_window) receives the next step of the plan, a list of actions:
- "text": click the widget whose text starts with it (button, radio button, check box)
- "encoder:HEVC GPU", "encoder:AV1 CPU": choose that kind of encoder; if this computer has none, the
  scenario is skipped (the window is closed: the application cancels)
- "wait:text": close the window once the text appears in it
- ["tree", row, column]: click a cell of the tree view (audio tracks)
The file dialogs answer with the files of the scenario, the yes/no questions with yes (or no when their
title is in the "refuse" list), and the message boxes are logged. The result (events, error) goes to
result.json in the folder of the scenario.
"""
import json
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
scenario = json.load(open(sys.argv[1], encoding="utf-8"))
sys.path.insert(0, ROOT)
os.chdir(scenario["workdir"])
events = []


def log(kind, *details):
    events.append([kind, *details])
    print(f"  [{kind}] " + " | ".join(str(d).replace("\n", " / ")[:200] for d in details), flush=True)


def ask_files(**options):
    return tuple(scenario["subtitles"] if "ubtitle" in options.get("title", "") else scenario["videos"])


sizes = scenario.get("size")


def ask_string(*args, **options):
    answer = sizes.pop(0) if isinstance(sizes, list) else sizes
    log("askstring", args[0], answer)
    return answer


def ask_yes_no(title, message, **options):
    answer = title not in scenario.get("refuse", [])
    log("askyesno", title, message, "yes" if answer else "no")
    return answer


filedialog.askopenfilenames = ask_files
filedialog.askopenfilename = lambda **options: ask_files(**options)[0]
filedialog.askdirectory = lambda **options: scenario["outdir"]
simpledialog.askstring = ask_string
messagebox.askyesno = messagebox.askokcancel = ask_yes_no
for kind in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, kind, lambda title, message, _kind=kind, **options: log(_kind, title, message))

if scenario.get("fake_google"):
    # Stand-in for Google Translate, with a network-like delay: "[fr] " + the text
    import gui_subtitle

    class FakeTranslator:
        def __init__(self, source, target):
            self.target = target

        def translate(self, text):
            time.sleep(0.05)
            return f"[{self.target}] {text}"
    gui_subtitle.GoogleTranslator = FakeTranslator

# The DeepL key is never saved in the profile of the user during the battery
import deepl  # noqa: E402
deepl.KEY_FILE = os.path.join(scenario["workdir"], "deepl_key.txt")
if scenario.get("fake_deepl"):
    # Stand-in for the DeepL API: "[deepl] " + the text; "quota": the quota is used up after the first batch
    batches = []

    def fake_batch(texts, key, source, target, url=None, sleep=None):
        batches.append(len(texts))
        if scenario["fake_deepl"] == "quota" and len(batches) > 1:
            raise deepl.DeepLError(deepl.ERRORS[456])
        return [f"[deepl] {text}" for text in texts]
    deepl.translate_batch = fake_batch

plan = list(scenario["plan"])


def widgets(widget):
    for child in widget.winfo_children():
        yield child
        yield from widgets(child)


def text_of(widget):
    try:
        return str(widget.cget("text")) if "text" in widget.keys() else ""
    except tk.TclError:
        return ""


def find(window, text):
    for widget in widgets(window):
        if text_of(widget).startswith(text):
            return widget
    raise LookupError(f"no widget {text!r} in {window.winfo_toplevel().title()!r}")


def all_text(window):
    texts = []
    for widget in widgets(window):
        texts.append(widget.get("1.0", "end") if isinstance(widget, tk.Text) else text_of(widget))
    return "\n".join(texts)


def act(window, action):
    if not window.winfo_exists():
        return
    if isinstance(action, list) and action[0] == "tree":
        tree = next(w for w in widgets(window) if isinstance(w, ttk.Treeview))
        x, y, width, height = tree.bbox(action[1], action[2])
        tree.event_generate("<Button-1>", x=x + width // 2, y=y + height // 2)
        log("click", f"tree row {action[1]}, column {action[2]}")
    elif action.startswith("wait:"):
        if action[5:] in all_text(window):
            log("seen", action[5:])
            window.destroy()
        else:
            window.after(500, act, window, action)
    elif action.startswith("encoder:"):
        codec, kind = action[8:].split()
        choices = [w for w in widgets(window) if text_of(w).startswith(f"{codec} - ") and kind in text_of(w)]
        if not choices:
            log("skip", f"no {codec} {kind} encoder on this computer")
            window.destroy()
            return
        log("click", text_of(choices[0]))
        choices[0].invoke()
    else:
        widget = find(window, action)
        log("click", action)
        widget.invoke()


def titles(window):
    names = [window.winfo_toplevel().title()] + [w.title() for w in widgets(window) if isinstance(w, tk.Toplevel)]
    return " / ".join(name for name in names if name)


def start_loop(window):
    step = plan.pop(0) if plan else []
    log("window", titles(window) or "(untitled)", f"{len(step)} action(s)")
    for i, action in enumerate(step, 1):
        window.after(400 * i, act, window, action)


original_mainloop, original_wait_window = tk.Misc.mainloop, tk.Misc.wait_window


def mainloop(self, n=0):
    start_loop(self)
    original_mainloop(self, n)


def wait_window(self, window=None):
    start_loop(window or self)
    original_wait_window(self, window)


tk.Misc.mainloop, tk.Misc.wait_window = mainloop, wait_window

start = time.time()
error = None
try:
    import main
    main.main()
except Exception as e:
    import traceback
    traceback.print_exc()
    error = f"{type(e).__name__}: {e}"
with open(os.path.join(scenario["workdir"], "result.json"), "w", encoding="utf-8") as f:
    json.dump({"events": events, "seconds": time.time() - start, "error": error, "unused_steps": plan}, f,
              ensure_ascii=False, indent=1)
