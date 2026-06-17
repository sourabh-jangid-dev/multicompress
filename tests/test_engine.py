"""Tests that the dispatcher routes each file type to the right compressor."""

from compressor.engine import detect_kind


def test_detect_kind_by_extension():
    assert detect_kind("a.mp4") == "video"
    assert detect_kind("a.MOV") == "video"      # case-insensitive
    assert detect_kind("a.jpg") == "image"
    assert detect_kind("a.png") == "image"
    assert detect_kind("a.mp3") == "audio"
    assert detect_kind("a.wav") == "audio"
    assert detect_kind("a.pdf") == "pdf"
    assert detect_kind("a.txt") == "archive"    # unknown -> archive fallback
    assert detect_kind("a.exe") == "archive"


def test_folder_is_archive(tmp_path):
    folder = tmp_path / "stuff"
    folder.mkdir()
    assert detect_kind(folder) == "archive"
