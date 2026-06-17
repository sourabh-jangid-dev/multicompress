"""
Tests for target-size mode, input validation, and HEIC routing.
"""

import random

import pytest
from PIL import Image

from compressor.engine import compress_path, detect_kind, validate_input
from compressor.image_compressor import compress_image_to_size


def _noisy_jpeg(path, size=(2500, 1800)):
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(0, size[1], 6):
        for x in range(0, size[0], 6):
            c = (random.randint(0, 255),) * 3
            for dy in range(6):
                for dx in range(6):
                    if x + dx < size[0] and y + dy < size[1]:
                        px[x + dx, y + dy] = c
    img.save(path, quality=95)


def test_heic_routes_to_image():
    assert detect_kind("photo.heic") == "image"
    assert detect_kind("photo.HEIF") == "image"


def test_validate_input(tmp_path):
    missing = tmp_path / "nope.jpg"
    assert validate_input(missing) == "file not found"

    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")
    assert validate_input(empty) == "file is empty"

    good = tmp_path / "ok.jpg"
    _noisy_jpeg(good, (400, 400))
    assert validate_input(good) is None


def test_image_target_size(tmp_path):
    src = tmp_path / "big.jpg"
    _noisy_jpeg(src)
    target = 90 * 1024  # 90 KB
    result = compress_image_to_size(src, tmp_path / "out", target)
    assert result["success"]
    # Should land at or under the target (with a little tolerance).
    assert result["compressed_bytes"] <= target * 1.05


def test_compress_path_rejects_empty(tmp_path):
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    result = compress_path(empty, tmp_path / "out", "balanced")
    assert not result["success"]
    assert result["error"] == "file is empty"


@pytest.mark.parametrize("target_kb", [60, 120])
def test_image_target_various(tmp_path, target_kb):
    src = tmp_path / f"img{target_kb}.jpg"
    _noisy_jpeg(src)
    result = compress_image_to_size(src, tmp_path / "out", target_kb * 1024)
    assert result["success"]
