"""
Integration tests: actually run each compressor on a generated sample file
and assert it produced a valid, not-larger output.

These use real Pillow / PyMuPDF / py7zr. They're fast because the samples
are tiny.
"""

import io
from pathlib import Path

import pytest
from PIL import Image

from compressor.archive_compressor import compress_archive
from compressor.image_compressor import compress_image
from compressor.pdf_compressor import compress_pdf
from compressor.presets import get_preset

PRESET = get_preset("small")


def _make_image(path: Path, size=(2000, 2000)):
    # A noisy image so it doesn't compress to nothing.
    import random
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(0, size[1], 10):
        for x in range(0, size[0], 10):
            c = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            for dy in range(10):
                for dx in range(10):
                    if x + dx < size[0] and y + dy < size[1]:
                        px[x + dx, y + dy] = c
    img.save(path, quality=95)


def test_image_compression_shrinks(tmp_path):
    src = tmp_path / "big.jpg"
    _make_image(src)
    out_dir = tmp_path / "out"
    result = compress_image(src, out_dir, PRESET)
    assert result["success"]
    assert Path(result["output"]).exists()
    assert result["compressed_bytes"] <= result["original_bytes"]


def test_pdf_compression_runs(tmp_path):
    import fitz
    src = tmp_path / "doc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    buf = io.BytesIO()
    _img = Image.new("RGB", (1500, 2000), (40, 120, 90))
    _img.save(buf, "JPEG", quality=95)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(src)
    doc.close()

    out_dir = tmp_path / "out"
    result = compress_pdf(src, out_dir, PRESET)
    assert result["success"]
    assert Path(result["output"]).exists()


def test_archive_compresses_text(tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("hello world\n" * 20000, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = compress_archive(src, out_dir, PRESET)
    assert result["success"]
    # Highly repetitive text should compress a lot.
    assert result["compressed_bytes"] < result["original_bytes"]


@pytest.mark.parametrize("ext", [".jpg", ".png"])
def test_image_formats(tmp_path, ext):
    src = tmp_path / f"img{ext}"
    _make_image(src, size=(800, 800))
    result = compress_image(src, tmp_path / "out", PRESET)
    assert result["success"]
