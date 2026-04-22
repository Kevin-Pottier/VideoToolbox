"""
Audio Track Management Module
=============================
Provides functionality to detect, display, and process audio tracks in video files.
Uses ffprobe JSON output for robust stream detection.
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional
from colorama import Fore, Style


@dataclass
class AudioTrackInfo:
    """
    Represents an audio stream in a video file.
    
    Attributes:
        stream_index: Index of the stream in the source file (0-based)
        language: Language tag (e.g., 'eng', 'fre'), or None if not set
        title: Track title, or None if not set
        codec: Audio codec name (e.g., 'aac', 'ac3', 'dts')
        channels: Number of audio channels (e.g., 2, 6)
        channel_layout: Channel layout (e.g., 'stereo', '5.1(side)')
        bit_rate: Bit rate in bps, or None
        is_default: Whether this track is marked as default in source
        disposition: Raw disposition flags from ffprobe
    """
    stream_index: int
    language: Optional[str] = None
    title: Optional[str] = None
    codec: Optional[str] = None
    channels: Optional[int] = None
    channel_layout: Optional[str] = None
    bit_rate: Optional[int] = None
    is_default: bool = False
    disposition: int = 0
    
    @property
    def display_name(self) -> str:
        """Generate a human-readable name for the track."""
        parts = []
        
        # Language or fallback
        if self.language:
            parts.append(self.language.upper())
        else:
            parts.append(f"Audio #{self.stream_index}")
        
        # Title if available
        if self.title:
            parts.append(f"({self.title})")
        
        # Channels
        if self.channels:
            ch_str = f"{self.channels}ch"
            if self.channel_layout:
                ch_str += f" {self.channel_layout}"
            parts.append(ch_str)
        
        # Codec
        if self.codec:
            parts.append(self.codec.upper())
        
        # Default indicator
        if self.is_default:
            parts.append("[DEFAULT]")
        
        return " ".join(parts)
    
    @property
    def short_description(self) -> str:
        """Short description for UI lists."""
        lang = self.language.upper() if self.language else "?"
        channels = f"{self.channels}ch" if self.channels else "?"
        codec = self.codec.upper() if self.codec else "?"
        default_mark = " ★" if self.is_default else ""
        return f"{lang} | {channels} | {codec}{default_mark}"


@dataclass
class VideoTrackInfo:
    """Represents the video stream in a file."""
    stream_index: int
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bit_rate: Optional[int] = None
    duration: Optional[float] = None


@dataclass
class SubtitleTrackInfo:
    """Represents a subtitle stream in a file."""
    stream_index: int
    language: Optional[str] = None
    title: Optional[str] = None
    codec: Optional[str] = None  # e.g., 'subrip', 'ass'
    is_default: bool = False


@dataclass
class MediaFileInfo:
    """
    Complete information about a media file's streams.
    
    Attributes:
        file_path: Path to the media file
        video_tracks: List of video streams
        audio_tracks: List of audio streams
        subtitle_tracks: List of subtitle streams
        duration: Total duration in seconds
        format_name: Container format (e.g., 'matroska', 'mov,mp4,m4a,3gp,3g2,mj2')
    """
    file_path: str
    video_tracks: list[VideoTrackInfo] = field(default_factory=list)
    audio_tracks: list[AudioTrackInfo] = field(default_factory=list)
    subtitle_tracks: list[SubtitleTrackInfo] = field(default_factory=list)
    duration: Optional[float] = None
    format_name: Optional[str] = None


def ffprobe_streams(file_path: str) -> MediaFileInfo:
    """
    Execute ffprobe and parse JSON output to extract all stream information.
    
    Args:
        file_path: Path to the media file
        
    Returns:
        MediaFileInfo object containing all stream information
        
    Raises:
        RuntimeError: If ffprobe fails or output cannot be parsed
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        
        data = json.loads(result.stdout)
        
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe JSON output: {e}")
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Ensure FFmpeg is installed and in PATH.")
    
    # Extract format info
    format_info = data.get("format", {})
    duration = None
    if format_info.get("duration"):
        try:
            duration = float(format_info["duration"])
        except (ValueError, TypeError):
            pass
    
    format_name = format_info.get("format_name")
    
    # Parse streams
    video_tracks = []
    audio_tracks = []
    subtitle_tracks = []
    
    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        
        if codec_type == "video":
            video_tracks.append(VideoTrackInfo(
                stream_index=stream.get("index", 0),
                codec=stream.get("codec_name"),
                width=stream.get("width"),
                height=stream.get("height"),
                bit_rate=int(stream["bit_rate"]) if stream.get("bit_rate") else None,
                duration=float(stream["duration"]) if stream.get("duration") else None
            ))
            
        elif codec_type == "audio":
            # Parse disposition flags
            disposition = stream.get("disposition", {})
            is_default = bool(disposition.get("default", 0))
            
            # Extract language from tags or disposition
            language = None
            tags = stream.get("tags", {})
            if tags:
                language = tags.get("language") or tags.get("lang")
            
            audio_tracks.append(AudioTrackInfo(
                stream_index=stream.get("index", 0),
                language=language,
                title=tags.get("title"),
                codec=stream.get("codec_name"),
                channels=stream.get("channels"),
                channel_layout=stream.get("channel_layout"),
                bit_rate=int(stream["bit_rate"]) if stream.get("bit_rate") else None,
                is_default=is_default,
                disposition=disposition.get("default", 0)
            ))
            
        elif codec_type == "subtitle":
            disposition = stream.get("disposition", {})
            is_default = bool(disposition.get("default", 0))
            
            tags = stream.get("tags", {})
            language = None
            if tags:
                language = tags.get("language") or tags.get("lang")
            
            subtitle_tracks.append(SubtitleTrackInfo(
                stream_index=stream.get("index", 0),
                language=language,
                title=tags.get("title"),
                codec=stream.get("codec_name"),
                is_default=is_default
            ))
    
    return MediaFileInfo(
        file_path=file_path,
        video_tracks=video_tracks,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
        duration=duration,
        format_name=format_name
    )


@dataclass
class AudioProcessingOptions:
    """
    User's choices for audio track processing.
    
    Attributes:
        keep_all_audio: If True, keep all audio tracks
        selected_tracks: List of source stream indices to keep (if not keeping all)
        default_track_index: Source stream index to set as default (if multiple tracks)
        keep_video: Whether to keep the video track
        keep_subtitles: Whether to keep subtitle tracks
        reencode_video: Whether to reencode video (False = copy)
        reencode_audio: Whether to reencode audio (False = copy)
    """
    keep_all_audio: bool = False
    selected_tracks: list[int] = field(default_factory=list)
    default_track_index: Optional[int] = None
    keep_video: bool = True
    keep_subtitles: bool = True
    reencode_video: bool = False
    reencode_audio: bool = False


def build_audio_mapping_options(
    media_info: MediaFileInfo,
    options: AudioProcessingOptions
) -> dict:
    """
    Build FFmpeg mapping and disposition options based on user choices.
    
    This function separates UI-agnostic logic from FFmpeg command building.
    
    Args:
        media_info: Parsed media file information
        options: User's processing options
        
    Returns:
        Dictionary with keys:
            - 'video_map': Video map string (e.g., "0:v")
            - 'audio_maps': List of audio map strings
            - 'subtitle_maps': List of subtitle map strings
            - 'disposition_args': List of disposition FFmpeg arguments
            - 'video_codec': Video codec string
            - 'audio_codec': Audio codec string
            - 'needs_encoding': Whether any reencoding is needed
    """
    video_map = None
    audio_maps = []
    subtitle_maps = []
    disposition_args = []
    needs_encoding = False
    
    # Video mapping
    if options.keep_video and media_info.video_tracks:
        video_map = "0:v"
        if options.reencode_video:
            needs_encoding = True
    
    # Audio mapping
    if options.keep_all_audio:
        # Keep all audio tracks
        audio_maps = [f"0:a:{i}" for i in range(len(media_info.audio_tracks))]
    elif options.selected_tracks:
        # Keep only selected tracks
        for src_idx in options.selected_tracks:
            # Find the position of this stream in the audio track list
            for i, track in enumerate(media_info.audio_tracks):
                if track.stream_index == src_idx:
                    audio_maps.append(f"0:a:{i}")
                    break
    
    # Determine if audio needs reencoding
    if audio_maps and options.reencode_audio:
        needs_encoding = True
    
    # Subtitle mapping
    if options.keep_subtitles and media_info.subtitle_tracks:
        subtitle_maps = [f"0:s:{i}" for i in range(len(media_info.subtitle_tracks))]
    
    # Build disposition for default audio track
    if len(audio_maps) > 1 and options.default_track_index is not None:
        # Find the input index (position in media_info.audio_tracks) of the default track
        default_input_index = next(
            (idx for idx, track in enumerate(media_info.audio_tracks)
             if track.stream_index == options.default_track_index),
            None
        )
        
        if default_input_index is not None:
            # For each audio map, determine if it's the default track
            for j, audio_map in enumerate(audio_maps):
                # Extract the source audio index from the map (e.g., "0:a:2" -> 2)
                source_index = int(audio_map.split(":")[-1])
                
                if source_index == default_input_index:
                    # This is the default track
                    disposition_args.extend(["-disposition:a:" + str(j), "default"])
                else:
                    # Clear the default flag
                    disposition_args.extend(["-disposition:a:" + str(j), "0"])
    
    elif len(audio_maps) == 1 and options.default_track_index is not None:
        # Single track - just ensure it's default
        disposition_args.extend(["-disposition:a:0", "default"])
    
    # Codec selection
    video_codec = "copy" if not options.reencode_video else "libx264"
    audio_codec = "copy" if not options.reencode_audio else "aac"
    
    return {
        "video_map": video_map,
        "audio_maps": audio_maps,
        "subtitle_maps": subtitle_maps,
        "disposition_args": disposition_args,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "needs_encoding": needs_encoding
    }


def build_ffmpeg_command(
    input_file: str,
    output_file: str,
    mapping_info: dict
) -> list[str]:
    """
    Build the complete FFmpeg command from mapping information.
    
    Args:
        input_file: Source video file path
        output_file: Destination file path
        mapping_info: Output from build_audio_mapping_options()
        
    Returns:
        List of command arguments for subprocess
    """
    cmd = ["ffmpeg", "-i", input_file]
    
    # Add video map
    video_map = mapping_info.get("video_map")
    if video_map:
        cmd.extend(["-map", video_map])
    
    # Add audio maps
    for audio_map in mapping_info.get("audio_maps", []):
        cmd.extend(["-map", audio_map])
    
    # Add subtitle maps
    for sub_map in mapping_info.get("subtitle_maps", []):
        cmd.extend(["-map", sub_map])
    
    # Add codecs
    video_codec = mapping_info.get("video_codec", "copy")
    audio_codec = mapping_info.get("audio_codec", "copy")
    
    cmd.extend(["-c:v", video_codec])
    cmd.extend(["-c:a", audio_codec])
    cmd.extend(["-c:s", "copy"])  # Always copy subtitles
    
    # Add disposition args
    disposition_args = mapping_info.get("disposition_args", [])
    cmd.extend(disposition_args)
    
    # Add movflags for MP4
    if output_file.lower().endswith(".mp4"):
        cmd.extend(["-movflags", "+faststart"])
    
    # Output file and overwrite flag
    cmd.extend([output_file, "-y"])
    
    return cmd


def generate_audio_extraction_command(
    input_file: str,
    output_file: str,
    audio_track_index: int,
    codec: str = "copy"
) -> list[str]:
    """
    Generate a simple FFmpeg command to extract a single audio track.
    
    Args:
        input_file: Source video file
        output_file: Destination audio file
        audio_track_index: Source stream index to extract
        codec: Audio codec ('copy', 'mp3', 'aac', 'flac', etc.)
        
    Returns:
        FFmpeg command as list of strings
    """
    return [
        "ffmpeg",
        "-i", input_file,
        "-map", f"0:a:{audio_track_index}",
        "-c:a", codec,
        output_file,
        "-y"
    ]


# ============================================================================
# EXAMPLE USAGE AND TESTING
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python audio_tracks.py <video_file>")
        sys.exit(1)
    
    video_file = sys.argv[1]
    
    print(Fore.CYAN + "=" * 60)
    print("Audio Track Detection Test")
    print("=" * 60 + Style.RESET_ALL)
    
    try:
        media_info = ffprobe_streams(video_file)
        
        print(f"\nFile: {media_info.file_path}")
        print(f"Format: {media_info.format_name}")
        print(f"Duration: {media_info.duration:.2f}s" if media_info.duration else "Duration: Unknown")
        
        print(Fore.YELLOW + "\n--- Video Tracks ---" + Style.RESET_ALL)
        for track in media_info.video_tracks:
            print(f"  [{track.stream_index}] {track.codec} - {track.width}x{track.height}")
        
        print(Fore.YELLOW + "\n--- Audio Tracks ---" + Style.RESET_ALL)
        for track in media_info.audio_tracks:
            print(f"  [{track.stream_index}] {track.display_name}")
            print(f"      {track.short_description}")
        
        print(Fore.YELLOW + "\n--- Subtitle Tracks ---" + Style.RESET_ALL)
        for track in media_info.subtitle_tracks:
            lang = track.language or "?"
            title = f" - {track.title}" if track.title else ""
            default = " [DEFAULT]" if track.is_default else ""
            print(f"  [{track.stream_index}] {lang}{title} ({track.codec}){default}")
        
        # Example: Select first audio track as default
        if media_info.audio_tracks:
            options = AudioProcessingOptions(
                keep_all_audio=False,
                selected_tracks=[media_info.audio_tracks[0].stream_index],
                default_track_index=media_info.audio_tracks[0].stream_index,
                keep_video=True,
                keep_subtitles=True
            )
            
            mapping = build_audio_mapping_options(media_info, options)
            cmd = build_ffmpeg_command(video_file, "output.mp4", mapping)
            
            print(Fore.GREEN + "\n--- Example FFmpeg Command ---" + Style.RESET_ALL)
            print(" ".join(cmd))
    
    except RuntimeError as e:
        print(Fore.RED + f"Error: {e}" + Style.RESET_ALL)
        sys.exit(1)