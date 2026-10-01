"""
GUI for Audio Track Management
===============================
Provides a user interface to detect, select, and process audio tracks in video files.
Integrates with the existing VideoCompress application.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import os
import queue
import threading

# Import reusable GUI helpers
from gui_helpers import apply_modern_theme, create_styled_frame, create_styled_label, create_styled_button, show_message

# Import audio processing logic
from audio_tracks import (
    ffprobe_streams,
    MediaFileInfo,
    AudioProcessingOptions,
    build_audio_mapping_options,
    build_ffmpeg_command
)
import subprocess


def run_audio_tracks_gui():
    """
    Main entry point for the audio tracks management GUI.
    Follows the same pattern as other GUI modules in the application.
    """
    
    # Step 1: Select video file
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Choose video file",
        filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv")]
    )
    root.destroy()
    
    if not file_path:
        print(Fore.YELLOW + "No file selected. Cancelled." + Style.RESET_ALL)
        return
    
    print(Fore.CYAN + f"Selected file: {file_path}" + Style.RESET_ALL)
    
    # Step 2: Analyze file and show track selection UI
    try:
        print(Fore.YELLOW + "Analyzing media file with ffprobe..." + Style.RESET_ALL)
        media_info = ffprobe_streams(file_path)
        print(Fore.GREEN + f"✓ Found {len(media_info.audio_tracks)} audio track(s)" + Style.RESET_ALL)
        
    except FileNotFoundError:
        error_msg = "FFmpeg/FFprobe not found.\n\nPlease ensure FFmpeg is installed and in your system PATH."
        print(Fore.RED + "❌ FFmpeg not found" + Style.RESET_ALL)
        show_message("error", "❌ FFmpeg Not Found", error_msg)
        return
        
    except RuntimeError as e:
        error_msg = str(e)
        print(Fore.RED + f"❌ FFprobe error: {error_msg}" + Style.RESET_ALL)
        show_message("error", "❌ Analysis Error", f"Failed to analyze video file:\n\n{error_msg}")
        return
    
    if not media_info.audio_tracks:
        print(Fore.YELLOW + "No audio tracks found in file" + Style.RESET_ALL)
        show_message("info", "ℹ No Audio", "No audio tracks found in this video file.")
        return
    
    # Show the audio track selection window
    show_audio_selection_window(file_path, media_info)


def show_audio_selection_window(file_path: str, media_info: MediaFileInfo):
    """
    Display the main audio track selection interface with a beautiful table.
    
    Args:
        file_path: Path to the video file
        media_info: Parsed media information from ffprobe
    """
    from tkinter import ttk
    
    # Window setup
    selection_win = tk.Tk()
    selection_win.title("Audio Track Management")
    
    # Calculate window size
    num_tracks = len(media_info.audio_tracks)
    win_height = min(350 + num_tracks * 45, 650)
    
    selection_win.geometry(f"720x{win_height}")
    selection_win.configure(bg="#23272e")
    selection_win.attributes('-topmost', True)
    
    # Center window
    selection_win.update_idletasks()
    w = selection_win.winfo_width()
    h = win_height
    x = (selection_win.winfo_screenwidth() // 2) - (w // 2)
    y = (selection_win.winfo_screenheight() // 2) - (h // 2)
    selection_win.geometry(f"{w}x{h}+{x}+{y}")
    
    apply_modern_theme(selection_win)
    
    # Main frame
    main_frame = create_styled_frame(selection_win)
    main_frame.pack(fill="both", expand=True, padx=15, pady=10)
    
    # Header
    create_styled_label(main_frame, "Audio Track Management", style='Title.TLabel').pack(pady=(0, 5))
    create_styled_label(main_frame, f"File: {os.path.basename(file_path)}", style='TLabel').pack(pady=(0, 8))
    
    # Track selection variables
    track_vars = {}  # stream_index -> BooleanVar (checkbox)
    default_var = tk.StringVar(master=selection_win)  # Selected default track stream_index (radio)
    
    # Table frame with border and header
    table_frame = tk.Frame(main_frame, bg="#1a1d23", bd=1, relief="solid")
    table_frame.pack(fill="both", expand=True, pady=10)
    
    # Header row
    header_canvas = tk.Canvas(table_frame, bg="#2d3037", height=40, highlightthickness=0)
    header_canvas.pack(fill="x")
    header_canvas.pack_propagate(False)
    
    # Header columns
    headers = [
        ("", 40),      # Checkbox column
        ("", 40),      # Default column  
        ("Index", 60),
        ("Language", 90),
        ("Channels", 80),
        ("Codec", 80),
        ("Title", 200)
    ]
    
    def draw_header():
        x_pos = 0
        for text, width in headers:
            bg_color = "#353b48"
            fg_color = "#4fd1c5"
            header_canvas.create_rectangle(x_pos, 0, x_pos + width, 40, fill=bg_color, outline="")
            if text:
                header_canvas.create_text(x_pos + width//2, 20, text=text, fill=fg_color, 
                                         font=("Segoe UI", 10, "bold"), anchor="center")
            x_pos += width
    
    header_canvas.bind("<Configure>", lambda e: header_canvas.delete("all") or draw_header())
    draw_header()
    header_canvas.pack()
    
    # Treeview for tracks (no headings, custom rendering)
    tree_frame = tk.Frame(table_frame, bg="#1a1d23")
    tree_frame.pack(fill="both", expand=True)
    
    # Custom treeview style
    style = ttk.Style(selection_win)
    style.theme_use("clam")
    style.configure("Treeview", 
                    background="#1a1d23", 
                    foreground="#f5f6fa",
                    fieldbackground="#1a1d23",
                    rowheight=38,
                    font=("Segoe UI", 10))
    style.configure("Treeview.Heading", 
                    background="#353b48", 
                    foreground="#4fd1c5",
                    font=("Segoe UI", 10, "bold"))
    style.map("Treeview", background=[("selected", "#4fd1c5")], foreground=[("selected", "#23272e")])
    
    # Create treeview
    columns = ("keep", "default", "index", "language", "channels", "codec", "title")
    tree = ttk.Treeview(tree_frame, columns=columns, show="", height=num_tracks)
    
    # Configure columns
    tree.column("keep", width=40, anchor="center")
    tree.column("default", width=40, anchor="center")
    tree.column("index", width=60, anchor="center")
    tree.column("language", width=90, anchor="center")
    tree.column("channels", width=80, anchor="center")
    tree.column("codec", width=80, anchor="center")
    tree.column("title", width=200, anchor="w")
    
    # Scrollbar
    scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    # Populate treeview with tracks
    for track in media_info.audio_tracks:
        stream_idx = track.stream_index
        
        # Create BooleanVar for checkbox (default: selected)
        track_vars[stream_idx] = tk.BooleanVar(value=True, master=selection_win)
        
        # Set default selection to first track or existing default
        if track.is_default or (default_var.get() == "" and stream_idx == media_info.audio_tracks[0].stream_index):
            default_var.set(str(stream_idx))
        
        # Format values
        lang = track.language.upper() if track.language else "—"
        ch = f"{track.channels}ch" if track.channels else "—"
        codec = track.codec.upper() if track.codec else "—"
        title = track.title if track.title else "—"
        if len(title) > 30:
            title = title[:27] + "..."
        
        # Insert row
        tree.insert("", "end", iid=str(stream_idx), values=("☐", "○", f"[{stream_idx}]", lang, ch, codec, title))
    
    # Bind click events for checkbox and radio functionality
    def on_tree_click(event):
        region = tree.identify_region(event.x, event.y)
        if region == "cell":
            column = tree.identify_column(event.x)
            item = tree.identify_row(event.y)
            if not item:
                return
            
            stream_idx = int(item)
            
            if column == "#1":  # Checkbox column
                # Toggle checkbox
                current = track_vars[stream_idx].get()
                track_vars[stream_idx].set(not current)
                # Update display
                new_val = "☐" if not current else "☑"
                tree.set(item, "keep", new_val)
                
            elif column == "#2":  # Default column
                # Set as default
                default_var.set(str(stream_idx))
                # Update all radio displays
                for idx in track_vars:
                    radio_val = "●" if idx == stream_idx else "○"
                    tree.set(str(idx), "default", radio_val)
    
    tree.bind("<Button-1>", on_tree_click)
    
    # Update display to show current state
    def refresh_display():
        for idx, var in track_vars.items():
            check_val = "☐" if not var.get() else "☑"
            radio_val = "●" if str(idx) == default_var.get() else "○"
            tree.set(str(idx), "keep", check_val)
            tree.set(str(idx), "default", radio_val)
    
    refresh_display()
    
    # Options frame
    options_frame = create_styled_frame(main_frame)
    options_frame.pack(fill="x", pady=8)
    
    keep_video_var = tk.BooleanVar(value=True, master=selection_win)
    keep_subs_var = tk.BooleanVar(value=True, master=selection_win)
    
    ttk.Checkbutton(options_frame, text="Keep video track", variable=keep_video_var, style='TCheckbutton').pack(anchor="w")
    ttk.Checkbutton(options_frame, text="Keep subtitle tracks", variable=keep_subs_var, style='TCheckbutton').pack(anchor="w", padx=(20, 0))
    
    # Container selection
    container_frame = create_styled_frame(main_frame)
    container_frame.pack(fill="x", pady=8)
    
    create_styled_label(container_frame, "Output container:").pack(side="left")
    
    container_var = tk.StringVar(value="mp4", master=selection_win)
    ttk.Radiobutton(container_frame, text="MP4", variable=container_var, value="mp4", style='TRadiobutton').pack(side="left", padx=10)
    ttk.Radiobutton(container_frame, text="MKV", variable=container_var, value="mkv", style='TRadiobutton').pack(side="left", padx=10)
    
    # Buttons
    btn_frame = create_styled_frame(main_frame)
    btn_frame.pack(fill="x", pady=(8, 0))
    
    choice = {}

    def on_process():
        # Collect selected tracks
        selected_tracks = [idx for idx, var in track_vars.items() if var.get()]
        
        if not selected_tracks:
            show_message("error", "Selection Error", "Please select at least one audio track to keep.")
            return
        
        # Get default track
        default_track = int(default_var.get()) if default_var.get() else selected_tracks[0]
        
        # Validate default is in selected
        if default_track not in selected_tracks:
            default_track = selected_tracks[0]
        
        # Read the choices while the window exists; the processing starts once its event loop has ended
        choice.update(selected_tracks=selected_tracks, default_track=default_track, keep_video=keep_video_var.get(),
                      keep_subs=keep_subs_var.get(), container=container_var.get())
        selection_win.destroy()
    
    def on_cancel():
        selection_win.destroy()
    
    create_styled_button(btn_frame, "Process", on_process).pack(side="right", padx=5)
    create_styled_button(btn_frame, "Cancel", on_cancel).pack(side="right", padx=5)
    
    selection_win.mainloop()
    if choice:
        process_audio_tracks(file_path, media_info, **choice)


def process_audio_tracks(
    file_path: str,
    media_info: MediaFileInfo,
    selected_tracks: list[int],
    default_track: int,
    keep_video: bool,
    keep_subs: bool,
    container: str
):
    """
    Process the video file with the selected audio track options.
    
    Args:
        file_path: Source video file
        media_info: Parsed media information
        selected_tracks: List of stream indices to keep
        default_track: Stream index to set as default
        keep_video: Keep the video track
        keep_subs: Keep the subtitle tracks
        container: Output container ('mp4' or 'mkv')
    """
    
    # Build options
    options = AudioProcessingOptions(
        keep_all_audio=False,
        selected_tracks=selected_tracks,
        default_track_index=default_track,
        keep_video=keep_video,
        keep_subtitles=keep_subs,
        reencode_video=False,
        reencode_audio=False
    )
    
    # Build FFmpeg mapping
    mapping_info = build_audio_mapping_options(media_info, options)
    
    # Determine output file
    base_name = os.path.splitext(file_path)[0]
    ext = container
    output_file = f"{base_name}_audio_processed.{ext}"
    
    # Build command
    ffmpeg_cmd = build_ffmpeg_command(file_path, output_file, mapping_info)
    
    # Verbose output
    print(Fore.CYAN + "\n" + "=" * 70)
    print("AUDIO TRACK PROCESSING")
    print("=" * 70 + Style.RESET_ALL)
    print(f"{Fore.GREEN}📁 Input:{Style.RESET_ALL}   {file_path}")
    print(f"{Fore.GREEN}📁 Output:{Style.RESET_ALL}  {output_file}")
    print()
    print(f"{Fore.YELLOW}🎵 Audio Tracks:{Style.RESET_ALL}")
    for track in media_info.audio_tracks:
        marker = "✓" if track.stream_index in selected_tracks else " "
        default_marker = " ★ DEFAULT" if track.stream_index == default_track else ""
        lang = track.language.upper() if track.language else "?"
        print(f"   [{marker}] Stream {track.stream_index}: {lang} | {track.channels}ch | {track.codec}{default_marker}")
    print()
    print(f"{Fore.YELLOW}📋 Options:{Style.RESET_ALL}")
    print(f"   Keep video: {keep_video}")
    print(f"   Keep subtitles: {keep_subs}")
    print(f"   Container: {ext.upper()}")
    print()
    print(f"{Fore.CYAN}🔧 FFmpeg Command:{Style.RESET_ALL}")
    print(f"   {' '.join(ffmpeg_cmd)}")
    print()

    if media_info.duration is None:
        messagebox.showerror("❌ Error", "Unable to determine the media duration.")
        return

    # Show progress window
    show_progress_window(file_path, output_file, ffmpeg_cmd, media_info.duration)


def show_progress_window(input_file: str, output_file: str, ffmpeg_cmd: list, duration: float):
    """
    Show a progress window during FFmpeg processing.
    
    Args:
        input_file: Source file
        output_file: Destination file
        ffmpeg_cmd: FFmpeg command to execute
        duration: Video duration in seconds
    """
    from tkinter import ttk
    import time
    import re
    
    progress_root = tk.Tk()
    progress_root.title("Processing Audio Tracks")
    progress_root.geometry("450x180")
    progress_root.attributes('-topmost', True)
    progress_root.configure(bg="#23272e")
    apply_modern_theme(progress_root)
    
    frame = create_styled_frame(progress_root)
    frame.pack(fill="both", expand=True, padx=15, pady=10)
    
    create_styled_label(
        frame,
        "Processing audio tracks...",
        style='Title.TLabel'
    ).pack(pady=(0, 8))
    
    create_styled_label(
        frame,
        os.path.basename(output_file),
        style='TLabel'
    ).pack(pady=(0, 8))
    
    progress_var = tk.DoubleVar(value=0, master=progress_root)
    progress_bar = ttk.Progressbar(
        frame,
        variable=progress_var,
        maximum=100,
        length=380,
        style='TProgressbar'
    )
    progress_bar.pack(pady=8)
    
    percent_label = create_styled_label(frame, "0%", style='TLabel')
    percent_label.pack()
    
    time_label = create_styled_label(
        frame,
        "Estimated time left: --:--",
        style='TLabel',
        font=("Segoe UI", 10, "italic")
    )
    time_label.pack()
    
    events = queue.Queue()  # the worker thread never touches Tk: it only fills this queue

    def run_ffmpeg():
        """Run FFmpeg in background thread; its progress and result go through the events queue."""
        video_dir = os.path.dirname(input_file) or "."
        error_output = []
        
        try:
            # ffmpeg writes UTF-8 (file names): the locale encoding (cp1252 on Windows) could fail on it
            proc = subprocess.Popen(
                ffmpeg_cmd,
                cwd=video_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace"
            )
            
            start_time = time.time()
            
            for line in proc.stderr:  # progress lines end with \r, split like \n
                # Capture error messages
                if any(err in line.lower() for err in ["error", "failed", "invalid"]):
                    error_output.append(line.strip())
                
                if "time=" in line:
                    match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                    if match and duration > 0:
                        h, m, s = match.groups()
                        cur_time = int(h) * 3600 + int(m) * 60 + float(s)
                        percent = min(100, int(cur_time / duration * 100))
                        
                        elapsed = time.time() - start_time
                        if cur_time > 0 and percent < 100:
                            est_total = elapsed / (cur_time / duration)
                            remaining = est_total - elapsed
                            mins, secs = divmod(int(remaining), 60)
                        else:
                            mins, secs = None, None
                        events.put(("progress", percent, mins, secs))
            
            proc.wait()
            
            if proc.returncode == 0:
                print(Fore.GREEN + "✅ Processing completed successfully!" + Style.RESET_ALL)
                events.put(("done", True, f"Audio tracks processed successfully!\n\nOutput: {os.path.basename(output_file)}"))
            else:
                if os.path.exists(output_file):
                    os.remove(output_file)  # a failed ffmpeg leaves an unreadable file that looks like a result
                error_msg = "\n".join(error_output[-5:]) if error_output else "Unknown error (check console for details)"
                print(Fore.RED + f"❌ Processing failed with code {proc.returncode}" + Style.RESET_ALL)
                print(Fore.RED + f"Error: {error_msg}" + Style.RESET_ALL)
                events.put(("done", False, f"Failed to process audio tracks.\n\nError: {error_msg}\n\nCheck console for full details."))
                
        except FileNotFoundError:
            error_msg = "FFmpeg not found. Please ensure FFmpeg is installed and in your PATH."
            print(Fore.RED + "❌ " + error_msg + Style.RESET_ALL)
            events.put(("done", False, error_msg))
            
        except Exception as e:
            print(Fore.RED + f"❌ Exception: {e}" + Style.RESET_ALL)
            events.put(("done", False, f"An unexpected error occurred:\n{e}"))
    
    def poll():
        """Apply the worker's events in the Tk thread."""
        try:
            while True:
                event = events.get_nowait()
                if event[0] == "progress":
                    _, percent, mins, secs = event
                    progress_var.set(percent)
                    percent_label.config(text=f"{percent}%")
                    if mins is not None:
                        time_label.config(text=f"Estimated time left: {mins:02d}:{secs:02d}")
                else:
                    _, ok, message = event
                    if ok:
                        progress_var.set(100)
                        percent_label.config(text="100%")
                        time_label.config(text="Completed!")
                        messagebox.showinfo("✅ Success", message, parent=progress_root)
                    else:
                        messagebox.showerror("❌ Error", message, parent=progress_root)
                    # Closed only once the message is acknowledged
                    progress_root.destroy()
                    return
        except queue.Empty:
            pass
        progress_root.after(200, poll)
    
    # Start processing in background thread
    thread = threading.Thread(target=run_ffmpeg, daemon=True)
    thread.start()
    poll()
    
    progress_root.mainloop()


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    run_audio_tracks_gui()