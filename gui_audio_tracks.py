"""
GUI for Audio Track Management
===============================
Provides a user interface to detect, select, and process audio tracks in video files.
Integrates with the existing VideoCompress application.
"""

import tkinter as tk
from tkinter import filedialog
from colorama import Fore, Style
import os

# Import reusable GUI helpers
from ffmpeg_progress import Cancelled, FFmpegError, run_ffmpeg
from gui_helpers import (VIDEO_TYPES, app_root, create_styled_frame, create_styled_label,
                         create_styled_button, new_window, run_jobs, show_message, show_results)

# Import audio processing logic
from audio_tracks import (
    ffprobe_streams,
    MediaFileInfo,
    AudioProcessingOptions,
    build_audio_mapping_options,
    build_ffmpeg_command
)


def run_audio_tracks_gui():
    """
    Main entry point for the audio tracks management GUI.
    Follows the same pattern as other GUI modules in the application.
    """
    
    # Step 1: Select video file
    file_path = filedialog.askopenfilename(parent=app_root(), title="Choose video file", filetypes=VIDEO_TYPES)
    
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
    
    # Window setup, its height following the number of tracks
    num_tracks = len(media_info.audio_tracks)
    selection_win, main_frame = new_window("Audio Track Management", f"720x{min(350 + num_tracks * 45, 650)}")
    
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
    
    selection_win.wait_window()
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

    def process(index, report, cancel):
        try:
            # Run in the folder of the video
            run_ffmpeg(ffmpeg_cmd, media_info.duration, report, cwd=os.path.dirname(file_path) or ".", cancel=cancel)
        except (FFmpegError, Cancelled):
            if os.path.exists(output_file):
                os.remove(output_file)  # a failed ffmpeg leaves an unreadable file that looks like a result
            raise
        print(Fore.GREEN + "✅ Processing completed successfully!" + Style.RESET_ALL)
        return output_file
    show_results("Audio tracks", run_jobs("Processing audio tracks", [os.path.basename(output_file)], process))


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    run_audio_tracks_gui()