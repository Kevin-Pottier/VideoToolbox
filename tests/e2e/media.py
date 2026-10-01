"""
Test media of the end-to-end battery, built from real footage downloaded once (about 15 MB, SHA-256 checked)
into the temporary folder of the system (not into the project, which may be synchronized, e.g. by OneDrive):
- classroom.mp4: 1080p30 camera video, 33 s (github.com/intel-iot-devkit/sample-videos)
- cockatoo.mp4: 720p hand-held video, 14 s (github.com/imageio/imageio-binaries)
- Megamind.avi: trailer of the movie, DivX (MPEG-4 with B-frames) 720x528, 11 s (github.com/opencv/opencv samples)
"""
import hashlib
import itertools
import os
import random
import shutil
import subprocess
import tempfile
import urllib.request

BASE = os.path.join(tempfile.gettempdir(), "videotoolbox_e2e")
DOWNLOADS = os.path.join(BASE, "media")
BUILT = os.path.join(DOWNLOADS, "built")
VERSION = "1"  # change it when the built media change: they are built again

SOURCES = {
    "classroom.mp4": ("https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/classroom.mp4",
                      "a69bd5e39ff0e74286d13bcbfdadddd307b85decd2d9853db7518e0028785e31"),
    "cockatoo.mp4": ("https://raw.githubusercontent.com/imageio/imageio-binaries/master/images/cockatoo.mp4",
                     "5fde35f5a288ca86e216d2dc28188ab64b4560d3021f273faefdf0de80f38aa5"),
    "Megamind.avi": ("https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/Megamind.avi",
                     "0057387cb7e75c8fd1663b62cfdc51fa53f527795d0fe3c1fea2fd159d3130b5"),
}

# Short classroom dialogue, shown over the 30 s film (the checks look for "Good morning")
DIALOGUE = ["Good morning, everyone.", "Please open your books at page twelve.", "Who can tell me what a resistor does?",
            "It limits the current in the circuit.", "Exactly, well done!", "And what about a capacitor?",
            "It stores energy in an electric field.", "We will measure it with the oscilloscope.",
            "Be careful with the power supply.", "Any questions before we start?"]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(name):
    url, expected = SOURCES[name]
    path = os.path.join(DOWNLOADS, name)
    if os.path.exists(path) and sha256(path) == expected:
        return path
    print(f"Downloading {name}...")
    urllib.request.urlretrieve(url, path + ".part")
    if sha256(path + ".part") != expected:
        os.remove(path + ".part")
        raise RuntimeError(f"{name}: unexpected SHA-256, the file at {url} changed")
    os.replace(path + ".part", path)
    return path


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path, lines, duration):
    step = duration / len(lines)
    with open(path, "w", encoding="utf-8") as f:
        for i, text in enumerate(lines):
            f.write(f"{i + 1}\n{srt_time(i * step + 0.05)} --> {srt_time((i + 1) * step - 0.05)}\n{text}\n\n")


def movie_lines(count=600):
    """Unique lines, as many as in a movie (the translation translates identical lines once)."""
    subjects = ["The engineer", "My brother", "The old captain", "Our teacher", "The young pilot", "Her neighbour",
                "The detective", "That stranger", "The mechanic", "Your sister"]
    verbs = ["found", "repaired", "lost", "painted", "sold", "opened", "measured", "hid", "carried", "forgot"]
    objects = ["the red car", "a broken radio", "the station's map", "an old letter", "the blue door", "a heavy box",
               "the kitchen clock", "a small boat", "the secret key", "the last train ticket"]
    endings = ["yesterday.", "before dawn.", "near the river.", "without telling anyone.", "in the rain.", "last summer."]
    combos = list(itertools.product(subjects, verbs, objects, endings))
    random.Random(1).shuffle(combos)
    return [" ".join(words) for words in combos[:count]]


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def build():
    """Download the footage and build the inputs of the scenarios (once). Returns the folder of the inputs."""
    marker = os.path.join(BUILT, f"version-{VERSION}")
    if os.path.exists(marker):
        return BUILT
    os.makedirs(BUILT, exist_ok=True)  # DOWNLOADS too
    classroom, cockatoo, megamind = (download(name) for name in SOURCES)
    print("Building the test media...")

    def out(name):
        return os.path.join(BUILT, name)
    write_srt(out("film.en.srt"), DIALOGUE, 30.0)
    write_srt(out("movie.en.srt"), movie_lines(), 600 * 3.0)
    # film.mkv: a VF/VO movie: English stereo first and default, French 5.1 second, English subtitles inside
    ffmpeg("-i", classroom,
           "-f", "lavfi", "-t", "32.8", "-i", "sine=frequency=440:sample_rate=48000,aformat=channel_layouts=stereo",
           "-f", "lavfi", "-t", "32.8", "-i", "anoisesrc=color=pink:amplitude=0.2:sample_rate=48000,aformat=channel_layouts=5.1",
           "-i", out("film.en.srt"),
           "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
           "-c:s", "srt", "-metadata:s:a:0", "language=eng", "-metadata:s:a:0", "title=English",
           "-metadata:s:a:1", "language=fre", "-metadata:s:a:1", "title=Français 5.1", "-metadata:s:s:0", "language=eng",
           "-disposition:a:0", "default", "-disposition:a:1", "0", "-shortest", out("film.mkv"))
    shutil.copyfile(cockatoo, out("cockatoo.mp4"))
    shutil.copyfile(megamind, out("megamind.avi"))
    # Short extracts: Real-ESRGAN without GPU (software Vulkan) takes seconds per frame
    ffmpeg("-i", megamind, "-t", "2", "-c:v", "libx264", "-crf", "16", "-c:a", "aac", out("megamind_2s.mkv"))
    ffmpeg("-i", megamind, "-frames:v", "12", "-t", "0.5", "-vf", "scale=360:-2", "-c:v", "libx264", "-crf", "16",
           "-c:a", "aac", out("megamind_small.mkv"))
    open(marker, "w").close()
    return BUILT


if __name__ == "__main__":
    print(build())
