import subprocess

def ffprobe(cmd):
    """
    Run ffprobe with the given command and return its output as a string.
    Args:
        cmd (list): List of command arguments for ffprobe.
    Returns:
        str: ffprobe output.
    """
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    return result.stdout.strip()