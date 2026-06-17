"""
engine.py
---------
The DISPATCHER (the "brain"). Given any file path, it looks at the extension
and routes the job to the correct compressor. The GUI and CLI both call ONLY
this module — they never need to know about the individual compressors.

Handles: file-type routing, target-size mode, cancellation, input validation,
history logging, and error logging.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from . import history
from .archive_compressor import compress_archive
from .audio_compressor import compress_audio, compress_audio_to_size
from .image_compressor import compress_image, compress_image_to_size
from .logsetup import get_logger
from .pdf_compressor import compress_pdf, compress_pdf_to_size
from .presets import Preset, get_preset
from .utils import file_size, human_size
from .video_compressor import compress_video, compress_video_to_size

log = get_logger()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif",
              ".heic", ".heif"}  # .heic/.heif = iPhone photos (via pillow-heif)
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"}
PDF_EXTS = {".pdf"}


_ESTIMATE_RANGES = {
    "image": "~40–80%↓",
    "video": "~50–85%↓",
    "audio": "~60–85%↓",
    "pdf":   "~30–70%↓",
    "archive": "varies",
}


def estimate_reduction(path: str | Path) -> str:
    """Return a rough expected-reduction hint string for a file (no processing)."""
    return _ESTIMATE_RANGES.get(detect_kind(path), "varies")


def detect_kind(path: str | Path) -> str:
    """Return 'image' | 'video' | 'audio' | 'pdf' | 'archive'."""
    p = Path(path)
    if p.is_dir():
        return "archive"
    ext = p.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in PDF_EXTS:
        return "pdf"
    return "archive"  # fallback: pack anything else into .7z


def validate_input(path: str | Path) -> str | None:
    """
    Return None if the file looks compressible, else a short human reason.
    Catches the common real-world failures BEFORE we start work.
    """
    p = Path(path)
    if not p.exists():
        return "file not found"
    if p.is_dir():
        return None  # folders are valid (archived)
    try:
        if p.stat().st_size == 0:
            return "file is empty"
    except OSError:
        return "cannot read file"
    # Can we actually open it for reading? (Catches locked/permission-denied.)
    try:
        with open(p, "rb"):
            pass
    except PermissionError:
        return "file is locked or in use"
    except OSError:
        return "cannot open file"
    return None


def compress_path(input_path: str | Path,
                  output_dir: str | Path,
                  preset: str | Preset = "balanced",
                  progress_callback: Callable[[float], None] | None = None,
                  cancel_event: threading.Event | None = None,
                  target_mb: float | None = None) -> dict:
    """
    The one function everything else calls.

    `preset`    : a preset KEY (str) or a ready-made Preset object.
    `target_mb` : if set, use TARGET-SIZE mode (compress to under this many MB)
                  for video/image/audio. PDFs/archives ignore it (and say so).
    """
    kind = detect_kind(input_path)

    # --- Reliability gate: reject bad inputs with a clear reason -------------
    reason = validate_input(input_path)
    if reason is not None:
        log.warning("Skipped %s: %s", input_path, reason)
        return _error_result(kind, input_path, reason)

    preset_obj: Preset = preset if isinstance(preset, Preset) else get_preset(preset)
    target_bytes = int(target_mb * 1024 * 1024) if target_mb else None

    try:
        if target_bytes and kind in ("video", "image", "audio", "pdf"):
            result = _compress_to_size(kind, input_path, output_dir, target_bytes,
                                       preset_obj, progress_callback, cancel_event)
        elif kind == "image":
            result = compress_image(input_path, output_dir, preset_obj)
        elif kind == "pdf":
            result = compress_pdf(input_path, output_dir, preset_obj)
        elif kind == "video":
            result = compress_video(input_path, output_dir, preset_obj,
                                    progress_callback, cancel_event)
        elif kind == "audio":
            result = compress_audio(input_path, output_dir, preset_obj,
                                    progress_callback, cancel_event)
        else:
            result = compress_archive(input_path, output_dir, preset_obj)

        if kind not in ("video", "audio") and progress_callback:
            progress_callback(100.0)

        if not result.get("cancelled"):
            history.add_record(result)
        log.info("Compressed %s (%s) -> %s%% saved", input_path, kind,
                 result.get("saved_percent"))
        return result

    except MemoryError:
        log.exception("Out of memory on %s", input_path)
        return _error_result(kind, input_path, "not enough memory")
    except OSError as e:
        # Disk full, path too long, etc. — errno gives a hint.
        msg = "disk full" if getattr(e, "errno", None) == 28 else "disk/path error"
        log.exception("OSError on %s", input_path)
        return _error_result(kind, input_path, msg)
    except Exception as e:
        log.exception("Failed on %s", input_path)
        return _error_result(kind, input_path, str(e)[:60])


def _compress_to_size(kind, input_path, output_dir, target_bytes, preset_obj,
                      progress_callback, cancel_event) -> dict:
    """Route a target-size job to the right size-targeting compressor."""
    if kind == "video":
        return compress_video_to_size(input_path, output_dir, target_bytes,
                                      preset_obj.audio_bitrate,
                                      progress_callback, cancel_event)
    if kind == "audio":
        return compress_audio_to_size(input_path, output_dir, target_bytes,
                                      progress_callback, cancel_event)
    if kind == "pdf":
        result = compress_pdf_to_size(input_path, output_dir, target_bytes)
        if progress_callback:
            progress_callback(100.0)
        return result
    # image
    result = compress_image_to_size(input_path, output_dir, target_bytes,
                                    preset_obj.image_max_dim)
    if progress_callback:
        progress_callback(100.0)
    return result


def _error_result(kind, input_path, reason: str) -> dict:
    original = file_size(input_path) if os.path.exists(input_path) else 0
    return {
        "type": kind, "input": str(input_path), "output": "",
        "original_bytes": original, "compressed_bytes": original,
        "original_human": human_size(original), "compressed_human": human_size(original),
        "saved_percent": 0.0, "success": False, "error": reason, "cancelled": False,
    }
