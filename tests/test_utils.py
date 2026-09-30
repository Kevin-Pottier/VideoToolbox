import os

import pytest

from utils import prepare_subtitle_file, read_subtitle_text

SRT = "1\r\n00:00:00,000 --> 00:00:01,000\r\nLéa : « ça va » €\r\n"


@pytest.mark.parametrize("encoding, detected", [
    ("utf-8", "utf-8-sig"),
    ("utf-8-sig", "utf-8-sig"),  # the BOM is removed
    ("cp1252", "cp1252"),        # common for French .srt files
])
def test_read_subtitle_text_detects_the_encoding(tmp_path, encoding, detected):
    path = tmp_path / "sub.srt"
    path.write_bytes(SRT.encode(encoding))
    assert read_subtitle_text(str(path)) == (SRT, detected)


def test_read_subtitle_text_falls_back_to_latin1(tmp_path):
    path = tmp_path / "sub.srt"
    path.write_bytes(b"\x81 undefined in cp1252")
    text, encoding = read_subtitle_text(str(path))
    assert encoding == "latin-1"
    assert text == "\x81 undefined in cp1252"


def test_prepare_subtitle_file_copies_as_utf8_under_a_plain_name(tmp_path):
    source_dir = tmp_path / "autre dossier"
    source_dir.mkdir()
    source = source_dir / "Sous-titres l'été, [VF].SRT"
    source.write_bytes(SRT.encode("cp1252"))
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    dest = prepare_subtitle_file(str(source), str(work_dir))

    assert dest == os.path.join(str(work_dir), "subtitles.srt")
    assert open(dest, "rb").read() == SRT.encode("utf-8")  # line endings kept


@pytest.mark.parametrize("name, expected", [("styled.ass", "subtitles.ass"), ("no_extension", "subtitles.srt")])
def test_prepare_subtitle_file_keeps_the_subtitle_format(tmp_path, name, expected):
    source = tmp_path / name
    source.write_text("text", encoding="utf-8")
    assert os.path.basename(prepare_subtitle_file(str(source), str(tmp_path))) == expected
