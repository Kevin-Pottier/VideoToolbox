"""The DeepL client against a local stand-in of the DeepL API (its documented requests and answers)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import deepl


class FakeDeepL:
    """Answers like DeepL: "[FR] text" for each text, or the HTTP errors queued in statuses."""

    def __init__(self):
        self.requests = []
        self.statuses = []  # errors to answer first, one per request
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append((self.headers["Authorization"], body))
                status = fake.statuses.pop(0) if fake.statuses else 200
                answer = {"translations": [{"text": f"[{body['target_lang']}] {text}"} for text in body["text"]]}
                data = json.dumps(answer if status == 200 else {"message": "error"}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v2/translate"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def fake(monkeypatch):
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")  # the local stand-in, not through a proxy
    server = FakeDeepL()
    yield server
    server.server.shutdown()


def translate(fake, lines, **kwargs):
    return deepl.translate_lines(lines, "key:fx", "en", "fr", url=fake.url, sleep=lambda s: None, **kwargs)


def test_free_and_pro_keys_use_their_server():
    assert deepl.api_url("1234-abcd:fx") == "https://api-free.deepl.com/v2/translate"
    assert deepl.api_url("1234-abcd") == "https://api.deepl.com/v2/translate"


@pytest.mark.parametrize("code, source, target", [
    ("fr", "FR", "FR"), ("en", "EN", "EN-US"), ("pt", "PT", "PT-PT"), ("zh-CN", "ZH", "ZH-HANS"), ("iw", "HE", "HE"),
])
def test_language_codes(code, source, target):
    assert (deepl.source_code(code), deepl.target_code(code)) == (source, target)


def test_texts_go_by_batches_identical_ones_once(fake):
    lines = [f"Line {i}" for i in range(120)] + ["Yes.", "Yes.", ""]
    progress = []
    result = translate(fake, lines, on_progress=progress.append)
    assert result[:2] == ["[FR] Line 0", "[FR] Line 1"] and result[-3:] == ["[FR] Yes.", "[FR] Yes.", ""]
    assert [len(body["text"]) for _, body in fake.requests] == [50, 50, 21]  # 121 different texts
    assert {(auth, body["source_lang"], body["target_lang"]) for auth, body in fake.requests} == {
        ("DeepL-Auth-Key key:fx", "EN", "FR")}
    assert sum(progress) == len(lines) - 1  # every line but the empty one


def test_a_subtitle_on_two_lines_is_one_sentence_cut_again(fake):
    [result] = translate(fake, ["I don't know where\nhe has gone tonight."])
    assert fake.requests[0][1]["text"] == ["I don't know where he has gone tonight."]
    assert result.count("\n") == 1 and result.replace("\n", " ") == "[FR] I don't know where he has gone tonight."


def test_italic_tags_are_kept(fake):
    translate(fake, ["<i>Who's there?</i>", "Nobody."])
    assert fake.requests[0][1]["tag_handling"] == "html"


def test_a_busy_deepl_is_asked_again(fake):
    fake.statuses = [429, 503]
    assert translate(fake, ["Hello."]) == ["[FR] Hello."]
    assert len(fake.requests) == 3


@pytest.mark.parametrize("status, message", [(456, "quota"), (403, "refused the key"), (400, "language supported")])
def test_errors_say_why_and_keep_what_was_translated(fake, status, message):
    lines = [f"Line {i}" for i in range(60)]
    fake.statuses = [200, status]  # the second batch fails
    with pytest.raises(deepl.DeepLError, match=message) as error:
        translate(fake, lines)
    assert len(error.value.done) == 50 and error.value.done["Line 0"] == "[FR] Line 0"


def test_unreachable_deepl(monkeypatch):
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")
    with pytest.raises(deepl.DeepLError, match="cannot be reached"):
        deepl.translate_lines(["Hello."], "key", "en", "fr", url="http://127.0.0.1:9/v2/translate", sleep=lambda s: None)


@pytest.mark.parametrize("text, lines, expected", [
    ("Je ne sais pas où il est allé ce soir.", 2, "Je ne sais pas où il\nest allé ce soir."),
    ("Bonjour.", 2, "Bonjour."),        # one word: one line
    ("Bonjour à tous.", 1, "Bonjour à tous."),
    ("Un deux trois quatre cinq six sept huit neuf", 3, "Un deux trois\nquatre cinq six\nsept huit neuf"),
])
def test_rewrap(text, lines, expected):
    assert deepl.rewrap(text, lines) == expected


def test_the_key_comes_from_the_environment_or_the_saved_file(monkeypatch, tmp_path):
    monkeypatch.setattr(deepl, "KEY_FILE", str(tmp_path / "videotoolbox" / "deepl_key.txt"))
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    assert deepl.load_key() == ""
    deepl.save_key(" saved:fx \n")
    assert deepl.load_key() == "saved:fx"
    monkeypatch.setenv("DEEPL_API_KEY", "from-env:fx")
    assert deepl.load_key() == "from-env:fx"
