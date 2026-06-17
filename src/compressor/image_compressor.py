"""
image_compressor.py
-------------------
Compresses a single image (JPG / PNG / WebP / HEIC ...) using Pillow.

LIBRARY: Pillow (imported as `PIL`), plus pillow-heif for iPhone .heic photos.

HOW IMAGE COMPRESSION ACTUALLY WORKS (teaching):
  Two levers shrink an image:
    1) RESOLUTION — fewer pixels = smaller file. (Biggest impact!)
    2) QUALITY    — JPEG/WebP throw away detail the eye barely notices.

This module also supports TARGET-SIZE mode: keep lowering quality (and, if
needed, resolution) until the file fits under a requested size in MB.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps  # Pillow's main classes

from .presets import Preset
from .utils import build_output_path, file_size, human_size, reduction_percent, safe_copy

# Register HEIC/HEIF support so Pillow can open iPhone photos. Optional: if the
# package isn't installed, .heic just won't be supported (no crash).
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    _HEIC_OK = True
except Exception:
    _HEIC_OK = False

# Extensions that we re-encode to JPEG (no transparency, photographic).
_TO_JPEG = {".jpg", ".jpeg", ".heic", ".heif"}


def _prepare(input_path: Path, max_dim: int):
    """
    Open an image, fix orientation, and shrink it to fit `max_dim`.
    Returns (pil_image, out_ext, save_kwargs_builder).

    save_kwargs_builder(quality) -> (kwargs, supports_quality) lets the caller
    re-save at different qualities without re-opening the file.
    """
    img = Image.open(input_path)
    if img.format == "JPEG":
        img.draft("RGB", (max_dim, max_dim))         # faster/low-RAM decode
    img = ImageOps.exif_transpose(img)               # respect phone rotation flag
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)  # downscale if too big

    ext = input_path.suffix.lower()
    if ext in _TO_JPEG:
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")                  # JPEG has no transparency
        out_ext = ".jpg"

        def builder(q):
            return dict(format="JPEG", quality=q, optimize=True, progressive=True), True
    elif ext == ".png":
        out_ext = ".png"

        def builder(q):
            return dict(format="PNG", optimize=True, compress_level=9), False
    else:
        if img.mode == "P":
            img = img.convert("RGBA")
        out_ext = ".webp"

        def builder(q):
            return dict(format="WEBP", quality=q, method=6), True

    return img, out_ext, builder


def compress_image(input_path: str | Path, output_dir: str | Path,
                   preset: Preset) -> dict:
    """Compress ONE image at the preset's quality. Returns a report dict."""
    input_path = Path(input_path)
    original_bytes = file_size(input_path)

    img, out_ext, builder = _prepare(input_path, preset.image_max_dim)
    save_kwargs, _ = builder(preset.image_quality)
    output_path = build_output_path(input_path, output_dir, new_ext=out_ext)
    img.save(output_path, **save_kwargs)
    img.close()

    return _finish(input_path, output_path, output_dir, original_bytes)


def compress_image_to_size(input_path: str | Path, output_dir: str | Path,
                           target_bytes: int, max_dim: int = 4000) -> dict:
    """
    TARGET-SIZE mode: shrink the image until it fits under `target_bytes`.

    Strategy:
      1. Binary-search the quality (10..95) for the best one that fits.
      2. If even quality=10 is too big, scale the resolution down 20% and retry
         (up to a few times). This guarantees we converge for any target.
    """
    input_path = Path(input_path)
    original_bytes = file_size(input_path)
    out_ext = ".jpg" if input_path.suffix.lower() in _TO_JPEG else \
        (".png" if input_path.suffix.lower() == ".png" else ".webp")
    output_path = build_output_path(input_path, output_dir, new_ext=out_ext)

    # Start from the image's ACTUAL longest side (never bigger than max_dim) so
    # our resolution-reduction steps take effect immediately instead of wasting
    # iterations trying to "shrink" an image that's already smaller than the cap.
    with Image.open(input_path) as _probe:
        dim = min(max_dim, max(_probe.size))
    best_bytes: bytes | None = None

    for _attempt in range(7):  # up to 7 resolution steps
        img, out_ext, builder = _prepare(input_path, dim)
        _, supports_quality = builder(50)

        if not supports_quality:
            # PNG has no quality knob — just save once at this resolution.
            buf = io.BytesIO()
            kwargs, _ = builder(0)
            img.save(buf, **kwargs)
            data = buf.getvalue()
            if len(data) <= target_bytes or _attempt == 4:
                best_bytes = data
                img.close()
                break
            img.close()
            dim = int(dim * 0.72)
            continue

        # Binary search quality for the largest one that fits the target.
        lo, hi, chosen = 10, 95, None
        while lo <= hi:
            mid = (lo + hi) // 2
            buf = io.BytesIO()
            kwargs, _ = builder(mid)
            img.save(buf, **kwargs)
            size = buf.tell()
            if size <= target_bytes:
                chosen = buf.getvalue()
                lo = mid + 1          # try for higher quality
            else:
                hi = mid - 1
        img.close()

        if chosen is not None:
            best_bytes = chosen
            break
        dim = int(dim * 0.72)          # even lowest quality too big -> smaller res

    if best_bytes is None:
        # Couldn't hit the target; keep the smallest attempt we made.
        img, out_ext, builder = _prepare(input_path, dim)
        buf = io.BytesIO()
        kwargs, _ = builder(10)
        img.save(buf, **kwargs)
        best_bytes = buf.getvalue()
        img.close()

    Path(output_path).write_bytes(best_bytes)
    return _finish(input_path, output_path, output_dir, original_bytes)


def _finish(input_path: Path, output_path, output_dir, original_bytes: int) -> dict:
    """Build the report dict, keeping the original if we accidentally grew it."""
    compressed_bytes = file_size(output_path)
    if compressed_bytes >= original_bytes and original_bytes > 0:
        fallback = build_output_path(input_path, output_dir, new_ext=input_path.suffix)
        safe_copy(input_path, fallback)
        output_path = fallback
        compressed_bytes = original_bytes

    return {
        "type": "image",
        "input": str(input_path),
        "output": str(output_path),
        "original_bytes": original_bytes,
        "compressed_bytes": compressed_bytes,
        "original_human": human_size(original_bytes),
        "compressed_human": human_size(compressed_bytes),
        "saved_percent": round(reduction_percent(original_bytes, compressed_bytes), 1),
        "success": True,
    }
