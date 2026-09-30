import threading

import pytest
from deep_translator import GoogleTranslator

from gui_subtitle import LANGUAGES, TranslationBlocked, translate_lines, translate_with_retry


def test_every_language_code_is_accepted_by_the_translator():
    # An unsupported code raised an exception in the worker thread and left the window stuck
    supported = set(GoogleTranslator(source="auto", target="en").get_supported_languages(as_dict=True).values())
    assert [(name, code) for name, code in LANGUAGES if code not in supported] == []


def test_language_codes_and_names_are_unique():
    codes = [code for _, code in LANGUAGES]
    names = [name for name, _ in LANGUAGES]
    assert len(set(codes)) == len(codes)
    assert len(set(names)) == len(names)


def test_default_languages_are_offered():
    codes = [code for _, code in LANGUAGES]
    assert "en" in codes and "fr" in codes  # defaults of the translation window


NO_WAIT = {"sleep": lambda seconds: None}


class FakeTranslator:
    """Upper-cases the text; fails for the texts in `failing`, or for the first `failures` calls."""
    instances = []

    def __init__(self, failing=(), failures=0):
        self.failing, self.failures, self.calls, self.threads = set(failing), failures, [], set()
        FakeTranslator.instances.append(self)

    def translate(self, text):
        self.calls.append(text)
        self.threads.add(threading.get_ident())
        if text in self.failing or len(self.calls) <= self.failures:
            raise ConnectionError("no network")
        return text.upper()


def test_retry_with_an_exponential_backoff():
    delays = []
    translator = FakeTranslator(failures=2)
    assert translate_with_retry(translator.translate, "hi", sleep=delays.append) == "HI"
    assert delays == [1.0, 2.0]


def test_retry_gives_up_after_the_last_attempt():
    delays = []
    with pytest.raises(ConnectionError):
        translate_with_retry(FakeTranslator(failing=["hi"]).translate, "hi", attempts=4, sleep=delays.append)
    assert delays == [1.0, 2.0, 4.0]


def test_blank_texts_are_not_sent():
    translator = FakeTranslator()
    assert translate_with_retry(translator.translate, "  ") == "  "
    assert translator.calls == []


def test_identical_lines_are_translated_once():
    FakeTranslator.instances = []
    lines = ["Yes.", "Thank you.", "Yes.", "Yes.", "Where?"]
    translated, failed = translate_lines(lines, FakeTranslator, workers=2)
    assert translated == ["YES.", "THANK YOU.", "YES.", "YES.", "WHERE?"]
    assert failed == 0
    assert sorted(call for t in FakeTranslator.instances for call in t.calls) == ["Thank you.", "Where?", "Yes."]


def test_each_worker_thread_has_its_own_translator():
    # A GoogleTranslator shared between threads can send the text of another thread
    FakeTranslator.instances = []
    translate_lines([f"line {i}" for i in range(200)], FakeTranslator, workers=4)
    assert all(len(t.threads) == 1 for t in FakeTranslator.instances)
    assert len({thread for t in FakeTranslator.instances for thread in t.threads}) == len(FakeTranslator.instances)


def test_failed_lines_are_kept_and_counted():
    lines = ["ok", "bad", "fine", "bad"]
    translated, failed = translate_lines(lines, lambda: FakeTranslator(failing=["bad"]), **NO_WAIT)
    assert translated == ["OK", "bad", "FINE", "bad"]
    assert failed == 2  # both occurrences of "bad"


def test_translation_stops_when_every_request_fails():
    FakeTranslator.instances = []
    lines = [f"line {i}" for i in range(100)]
    with pytest.raises(TranslationBlocked):
        translate_lines(lines, lambda: FakeTranslator(failing=lines), workers=2, max_consecutive_failures=5, **NO_WAIT)
    calls = sum(len(t.calls) for t in FakeTranslator.instances)
    assert calls < len(lines)  # stopped early instead of retrying every line


def test_progress_counts_every_line():
    done = []
    translate_lines(["a", "b", "a", "c"], FakeTranslator, on_progress=done.append)
    assert sum(done) == 4
