"""
pdf_compressor.py
-----------------
Shrinks a PDF by (1) downsampling + recompressing the images embedded in it,
then (2) stripping unused objects and deflating all streams.

LIBRARY: PyMuPDF (imported as `fitz`)
  A fast C-backed library for reading/editing PDFs. We use it to walk every
  page, find image objects, and swap them for smaller versions.

WHY PDFs ARE BIG (domain knowledge):
  A scanned or screenshot-heavy PDF stores each image at full resolution
  (often 2-4x more pixels than the page can ever show). Printed/displayed
  pages only need ~150 DPI. Downsampling those images is where the savings are.

  We approximate "too big" with a pixel cap derived from the target DPI:
      max_dim = dpi * 11   (11 in ~= the long side of a Letter/A4 page)
  Any embedded image bigger than that gets shrunk to fit.
"""

from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from .presets import Preset
from .utils import build_output_path, file_size, human_size, reduction_percent, safe_copy


def _do_compress(input_path: Path, output_path: Path,
                 max_dim: int, jpeg_quality: int) -> int:
    """Recompress all images in the PDF at the given settings; return out size."""
    doc = fitz.open(input_path)
    processed_xrefs: set[int] = set()
    for page in doc:
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in processed_xrefs:
                continue
            processed_xrefs.add(xref)
            try:
                _recompress_one_image(doc, page, xref, max_dim, jpeg_quality)
            except Exception:
                continue
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return file_size(output_path)


def compress_pdf(input_path: str | Path, output_dir: str | Path,
                 preset: Preset) -> dict:
    input_path = Path(input_path)
    original_bytes = file_size(input_path)
    output_path = build_output_path(input_path, output_dir, new_ext=".pdf")

    max_dim = preset.pdf_dpi * 11
    jpeg_quality = max(40, min(85, preset.image_quality))
    compressed_bytes = _do_compress(input_path, output_path, max_dim, jpeg_quality)

    if compressed_bytes >= original_bytes and original_bytes > 0:
        safe_copy(input_path, output_path)
        compressed_bytes = original_bytes
    return _report(input_path, output_path, original_bytes, compressed_bytes)


def compress_pdf_to_size(input_path: str | Path, output_dir: str | Path,
                         target_bytes: int) -> dict:
    """
    TARGET-SIZE mode for PDFs (useful for government portals that cap upload
    size, e.g. "under 500 KB"). We try progressively more aggressive
    DPI + JPEG-quality settings until the file fits under the target.
    """
    input_path = Path(input_path)
    original_bytes = file_size(input_path)
    output_path = build_output_path(input_path, output_dir, new_ext=".pdf")

    # GUARD: already small enough -> keep it.
    if 0 < original_bytes <= target_bytes:
        safe_copy(input_path, output_path)
        return _report(input_path, output_path, original_bytes, original_bytes,
                       note="already under target")

    # From gentle to very aggressive: (max image dimension in px, JPEG quality).
    steps = [(1800, 80), (1500, 70), (1200, 60), (1000, 50),
             (800, 40), (650, 35), (500, 30), (400, 25)]

    best = None
    for max_dim, q in steps:
        size = _do_compress(input_path, output_path, max_dim, q)
        if best is None or size < best:
            best = size
        if 0 < size <= target_bytes:
            return _report(input_path, output_path, original_bytes, size)

    # Couldn't reach the target; return the smallest we achieved (still useful).
    final = file_size(output_path)
    if final >= original_bytes:
        safe_copy(input_path, output_path)
        final = original_bytes
    return _report(input_path, output_path, original_bytes, final,
                   note="smallest achievable")


def _report(input_path, output_path, original_bytes, compressed_bytes,
            note: str = "") -> dict:
    return {
        "type": "pdf",
        "input": str(input_path),
        "output": str(output_path),
        "original_bytes": original_bytes,
        "compressed_bytes": compressed_bytes,
        "original_human": human_size(original_bytes),
        "compressed_human": human_size(compressed_bytes),
        "saved_percent": round(reduction_percent(original_bytes, compressed_bytes), 1),
        "success": True,
        "note": note,
    }


def _recompress_one_image(doc: fitz.Document, page: fitz.Page, xref: int,
                          max_dim: int, jpeg_quality: int) -> None:
    """
    Extract one embedded image, downscale + recompress it, and put it back.
    The leading underscore signals this is a 'private' helper for this module.
    """
    # extract_image returns the raw bytes + metadata (no decoding to pixels yet).
    base = doc.extract_image(xref)
    img_bytes = base["image"]

    # Load into Pillow so we can resize/re-encode.
    with Image.open(io.BytesIO(img_bytes)) as pil:
        w, h = pil.size

        # Skip tiny images (icons, logos) — not worth touching.
        if max(w, h) <= max_dim and base.get("ext") in ("jpg", "jpeg"):
            return

        # Downscale if larger than our cap (keeps aspect ratio).
        if max(w, h) > max_dim:
            pil.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Decide output encoding:
        #   - has transparency  -> keep PNG (JPEG can't do alpha)
        #   - otherwise         -> JPEG (far smaller for photos/scans)
        buf = io.BytesIO()
        if pil.mode in ("RGBA", "LA", "P"):
            pil.convert("RGBA").save(buf, format="PNG", optimize=True)
        else:
            pil.convert("RGB").save(buf, format="JPEG",
                                    quality=jpeg_quality, optimize=True)
        new_bytes = buf.getvalue()

    # Only replace if we actually got smaller.
    if len(new_bytes) < len(img_bytes):
        # replace_image swaps the bytes behind this xref everywhere it's used.
        page.replace_image(xref, stream=new_bytes)
