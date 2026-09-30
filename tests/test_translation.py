from deep_translator import GoogleTranslator

from gui_subtitle import LANGUAGES


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
