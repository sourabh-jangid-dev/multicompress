"""Unit tests for the small helper functions in utils.py."""

from compressor.utils import build_output_path, human_size, reduction_percent


def test_human_size_scales():
    assert human_size(0) == "0.00 B"
    assert human_size(1024) == "1.00 KB"
    assert human_size(1024 * 1024) == "1.00 MB"
    assert human_size(5 * 1024 * 1024 * 1024) == "5.00 GB"


def test_reduction_percent():
    assert reduction_percent(100, 30) == 70.0
    assert reduction_percent(100, 100) == 0.0
    # Guard against divide-by-zero on empty originals.
    assert reduction_percent(0, 0) == 0.0


def test_build_output_path(tmp_path):
    out = build_output_path("C:/x/clip.mp4", tmp_path, suffix="_c", new_ext=".mp4")
    assert out.name == "clip_c.mp4"
    assert out.parent == tmp_path
