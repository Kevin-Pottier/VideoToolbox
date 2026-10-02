"""
DeepL API client for the subtitle translation (https://www.deepl.com/pro-api): an official API, a free key gives
500,000 characters a month (a movie has about 50,000), and the French translations are better than Google's.

The texts go by batches of 50 (one request instead of 50). A subtitle on two lines is sent as one sentence and
cut again into the same number of lines afterwards, the line breaks of a subtitle being layout, not meaning.
"""
import json
import os
import time
import urllib.error
import urllib.request

BATCH_SIZE = 50  # texts per request (the maximum of DeepL)
ATTEMPTS = 4     # per request, waiting 1, 2, 4 s between them when DeepL is busy (429, 5xx) or unreachable
KEY_FILE = os.path.join(os.path.expanduser("~"), ".videotoolbox", "deepl_key.txt")

# Language codes of the application (those of Google Translate) that DeepL writes differently
SOURCE_CODES = {"zh-CN": "ZH", "no": "NB", "iw": "HE"}
TARGET_CODES = {"en": "EN-US", "pt": "PT-PT", "zh-CN": "ZH-HANS", "no": "NB", "iw": "HE"}
ERRORS = {
    400: "DeepL refused the request: is the language supported by DeepL?",
    403: "DeepL refused the key: check it on deepl.com (account, API keys).",
    456: "The DeepL quota of the month is used up.",
}


class DeepLError(RuntimeError):
    """DeepL could not translate: the message tells why. done holds the texts translated before."""

    def __init__(self, message, done=None):
        super().__init__(message)
        self.done = done or {}


def api_url(key):
    """Free keys end with ":fx" and use their own server."""
    return "https://api-free.deepl.com/v2/translate" if key.strip().endswith(":fx") else "https://api.deepl.com/v2/translate"


def source_code(code):
    return SOURCE_CODES.get(code, code.split("-")[0].upper())


def target_code(code):
    return TARGET_CODES.get(code, code.split("-")[0].upper())


def load_key():
    """The key of the DEEPL_API_KEY environment variable, else the one saved on this computer, else ""."""
    if os.environ.get("DEEPL_API_KEY"):
        return os.environ["DEEPL_API_KEY"].strip()
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_key(key):
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip())


def rewrap(text, line_count):
    """text cut into line_count lines of balanced length, at spaces (a single line stays as it is)."""
    words = text.split()
    if line_count <= 1 or len(words) < line_count:
        return " ".join(words)
    lines, start = [], 0
    for remaining in range(line_count, 1, -1):
        # The cut that makes the next line closest to an even share of what is left
        rest = " ".join(words[start:])
        share = len(rest) / remaining
        best, length = start + 1, len(words[start])
        for end in range(start + 1, len(words) - remaining + 2):
            candidate = len(" ".join(words[start:end]))
            if abs(candidate - share) <= abs(length - share):
                best, length = end, candidate
        lines.append(" ".join(words[start:best]))
        start = best
    lines.append(" ".join(words[start:]))
    return "\n".join(lines)


def translate_batch(texts, key, source, target, url=None, sleep=time.sleep):
    """Translations of the texts (at most BATCH_SIZE), in their order. Raises DeepLError."""
    body = {"text": texts, "source_lang": source_code(source), "target_lang": target_code(target)}
    if any("<" in text for text in texts):
        body["tag_handling"] = "html"  # keeps the <i> and <b> of the subtitles
    request = urllib.request.Request(url or api_url(key), data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"DeepL-Auth-Key {key.strip()}",
                                              "Content-Type": "application/json"})
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return [item["text"] for item in json.load(response)["translations"]]
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == ATTEMPTS - 1:
                raise DeepLError(ERRORS.get(e.code, f"DeepL answered with the error {e.code}.")) from e
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            if attempt == ATTEMPTS - 1:
                raise DeepLError(f"DeepL cannot be reached ({e}).") from e
        sleep(2 ** attempt)


def translate_lines(lines, key, source, target, on_progress=None, url=None, sleep=time.sleep):
    """
    Translate subtitle texts with DeepL, identical texts once.
    on_progress(number of lines done) is called after each batch.
    Returns:
        list: the translated lines.
    Raises:
        DeepLError: with done, the translations made before the failure (the caller can finish with Google).
    """
    positions = {}
    for index, text in enumerate(lines):
        positions.setdefault(text, []).append(index)
    unique = [text for text in positions if text.strip()]
    done = {text: text for text in positions if not text.strip()}  # nothing to translate
    for start in range(0, len(unique), BATCH_SIZE):
        batch = unique[start:start + BATCH_SIZE]
        try:
            translated = translate_batch([" ".join(text.split()) for text in batch], key, source, target, url, sleep)
        except DeepLError as e:
            e.done = done
            raise
        for text, translation in zip(batch, translated):
            done[text] = rewrap(translation, len(text.strip().splitlines()))
        if on_progress:
            on_progress(sum(len(positions[text]) for text in batch))
    return [done[text] for text in lines]
