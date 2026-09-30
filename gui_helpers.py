def apply_modern_theme(root, style=None):
    """
    Apply a modern ttk theme (azure-dark if available, else clam with custom palette) to the given root window.
    Returns the ttk.Style object.
    """
    from tkinter import ttk
    if style is None:
        style = ttk.Style(root)
    try:
        style.theme_use('azure-dark')
    except Exception:
        style.theme_use('clam')
        style.configure('TFrame', background="#23272e")
        style.configure('TLabel', background="#23272e", foreground="#f5f6fa", font=("Segoe UI", 11))
        style.configure('Title.TLabel', background="#23272e", foreground="#4fd1c5", font=("Segoe UI", 15, "bold"))
        style.configure('TButton', font=("Segoe UI", 12), padding=6, background="#353b48", foreground="#f5f6fa", borderwidth=0)
        style.map('TButton',
            background=[('active', '#4fd1c5'), ('!active', '#353b48')],
            foreground=[('active', '#23272e'), ('!active', '#f5f6fa')]
        )
        style.configure('TCheckbutton', background="#23272e", foreground="#f5f6fa", font=("Segoe UI", 10))
        style.configure('TRadiobutton', background="#23272e", foreground="#f5f6fa", font=("Segoe UI", 10))
        style.configure('TProgressbar', troughcolor="#23272e", background="#4fd1c5", thickness=18)
    return style

def create_styled_frame(root):
    from tkinter import ttk
    return ttk.Frame(root, style='TFrame')

def create_styled_label(parent, text, style='TLabel', **kwargs):
    from tkinter import ttk
    return ttk.Label(parent, text=text, style=style, background="#23272e", **kwargs)

def create_styled_button(parent, text, command, width=None):
    from tkinter import ttk
    return ttk.Button(parent, text=text, command=command, width=width, style='TButton')


def show_message(kind, title, message):
    """
    Show a message box ('error', 'info' or 'warning') above the other windows.
    It is attached to the open window when there is one: a second tk.Tk() would be a second
    Tcl interpreter, whose widgets and variables cannot be mixed with the first one's.
    """
    import tkinter as tk
    from tkinter import messagebox
    root = tk._default_root
    host = tk.Toplevel(root) if root is not None else tk.Tk()
    host.withdraw()
    host.attributes('-topmost', True)
    try:
        getattr(messagebox, f"show{kind}")(title, message, parent=host)
    finally:
        host.destroy()
