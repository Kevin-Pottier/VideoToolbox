import hashlib
import importlib.util
import os
import shutil
import stat
import sys
import zipfile

import pytest

import gui_upscale

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("fetch_deps", os.path.join(ROOT, "scripts", "fetch_deps.py"))
fetch_deps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_deps)


def test_every_archive_has_a_sha256():
    assert set(fetch_deps.ARCHIVES) == {"win32", "linux", "darwin"}
    for _, sha, _, _ in fetch_deps.ARCHIVES.values():
        assert len(sha) == 64 and int(sha, 16) >= 0


def test_executable_name_matches_gui_upscale():
    exe_name = fetch_deps.ARCHIVES[fetch_deps.platform_key()][2]
    assert os.path.basename(gui_upscale.REALESRGAN_EXE) == exe_name


@pytest.mark.parametrize("platform, key", [("linux", "linux"), ("win32", "win32"), ("darwin", "darwin")])
def test_platform_key(monkeypatch, platform, key):
    monkeypatch.setattr(sys, "platform", platform)
    assert fetch_deps.platform_key() == key


def fake_release(tmp_path):
    """A zip laid out like the official release, and its SHA-256."""
    exe_name = fetch_deps.ARCHIVES[fetch_deps.platform_key()][2]
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        models = [f"models/{m}.{ext}" for m in fetch_deps.MODELS for ext in ("bin", "param")]
        for name in [exe_name, "vcomp140.dll", "vcomp140d.dll", "onepiece_demo.mp4",
                     "models/realesrgan-x4plus-anime.bin", *models]:
            zf.writestr(name, f"content of {name}")
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def use_fake_release(monkeypatch, tmp_path, archive, sha):
    """Make fetch_deps "download" the given archive, expect the given SHA-256 and install into tmp_path/Tool."""
    key = fetch_deps.platform_key()
    suffix, _, exe_name, extra = fetch_deps.ARCHIVES[key]
    monkeypatch.setitem(fetch_deps.ARCHIVES, key, (suffix, sha, exe_name, extra))
    monkeypatch.setattr(fetch_deps, "download", lambda url, dest: shutil.copyfile(archive, dest))
    tool_dir = tmp_path / "Tool"
    monkeypatch.setattr(fetch_deps, "TOOL_DIR", str(tool_dir))
    return tool_dir


def test_install_extracts_only_the_files_used(monkeypatch, tmp_path):
    archive, sha = fake_release(tmp_path)
    tool_dir = use_fake_release(monkeypatch, tmp_path, archive, sha)

    assert fetch_deps.install_realesrgan(force=False, all_models=False)

    key = fetch_deps.platform_key()
    _, _, exe_name, extra = fetch_deps.ARCHIVES[key]
    extracted = sorted(os.path.relpath(os.path.join(d, f), tool_dir).replace(os.sep, "/")
                       for d, _, files in os.walk(tool_dir) for f in files)
    models = [f"models/{m}.{ext}" for m in fetch_deps.MODELS for ext in ("bin", "param")]
    assert extracted == sorted([exe_name, *extra, *models])
    if key != "win32":
        assert os.stat(tool_dir / exe_name).st_mode & stat.S_IXUSR


def test_install_rejects_an_archive_with_a_wrong_checksum(monkeypatch, tmp_path):
    archive, _ = fake_release(tmp_path)
    tool_dir = use_fake_release(monkeypatch, tmp_path, archive, "0" * 64)
    assert not fetch_deps.install_realesrgan(force=False, all_models=False)
    assert not tool_dir.exists()
