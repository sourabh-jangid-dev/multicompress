"""
utils.py
--------
Small helper functions used everywhere in the project.

TEACHING NOTE — why a "utils" file?
Instead of copy-pasting the same little helpers (like "turn 1500000 bytes into '1.5 MB'")
into every module, we write them ONCE here and import them. This is the DRY principle:
"Don't Repeat Yourself".
"""

from __future__ import annotations  # lets us use modern type hints on older Python too

import os
import shutil
import subprocess
import sys
from pathlib import Path


# ------------------------------------------------------------------
# Open a folder in the OS file manager — cross-platform.
# ------------------------------------------------------------------
def open_in_file_manager(path: str | Path) -> None:
    """
    Open `path` in Explorer (Windows), Finder (macOS) or the default file
    manager (Linux). Each OS has a different command, so we branch on platform.
    """
    path = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)                      # Windows
        elif sys.platform == "darwin":
            subprocess.run(["open", path])          # macOS
        else:
            subprocess.run(["xdg-open", path])      # Linux
    except Exception:
        pass


# ------------------------------------------------------------------
# 0) Locate bundled resources (icon, etc.) in BOTH dev and frozen .exe
# ------------------------------------------------------------------
def resource_path(relative: str) -> Path:
    """
    Return the absolute path to a bundled resource.

    When PyInstaller freezes the app it unpacks data files into a temp folder
    exposed as sys._MEIPASS. In normal development that attribute doesn't exist,
    so we fall back to the project root (two levels up from this file).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parents[2] / relative


# ------------------------------------------------------------------
# 1) Human-readable file sizes
# ------------------------------------------------------------------
def human_size(num_bytes: int) -> str:
    """
    Convert a raw byte count into something a human reads easily.
    Example: 1536000 -> '1.46 MB'

    Computers store size in bytes. 1 KB = 1024 bytes, 1 MB = 1024 KB, etc.
    We loop through the units, dividing by 1024 each time, until the number is small.
    """
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


# ------------------------------------------------------------------
# 2) How much did we save?
# ------------------------------------------------------------------
def reduction_percent(original: int, compressed: int) -> float:
    """
    Return the % reduction. Example: 100 MB -> 30 MB means 70% saved.
    We guard against divide-by-zero (an empty original file).
    """
    if original <= 0:
        return 0.0
    return (1 - compressed / original) * 100.0


# ------------------------------------------------------------------
# 3) LARGE-FILE-SAFE copy (chunked)
# ------------------------------------------------------------------
# TEACHING NOTE — this is the heart of "handles large files".
# If you do `data = open(file).read()` on a 5 GB video, Python tries to load
# ALL 5 GB into your 8 GB RAM at once -> the app freezes or crashes.
#
# Instead we read the file in small CHUNKS (e.g. 1 MB at a time), so memory
# usage stays tiny no matter how huge the file is. This is called "streaming".
CHUNK_SIZE = 1024 * 1024  # 1 MB per chunk


def safe_copy(src: str | Path, dst: str | Path) -> None:
    """Copy a file in 1 MB chunks so even a 50 GB file uses almost no RAM."""
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        # shutil.copyfileobj streams chunk-by-chunk internally — memory-safe.
        shutil.copyfileobj(fin, fout, CHUNK_SIZE)


# ------------------------------------------------------------------
# 4) Build a tidy output path
# ------------------------------------------------------------------
def build_output_path(input_path: str | Path, output_dir: str | Path,
                      suffix: str = "_compressed", new_ext: str | None = None) -> Path:
    """
    Given 'C:/videos/clip.mp4' and output dir 'C:/out',
    return 'C:/out/clip_compressed.mp4'.

    - suffix : added before the extension so we never overwrite the original.
    - new_ext: optionally change the extension (e.g. '.png' -> '.webp').
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)  # create the folder if missing

    ext = new_ext if new_ext else input_path.suffix
    return output_dir / f"{input_path.stem}{suffix}{ext}"


# ------------------------------------------------------------------
# 5) Get file size safely
# ------------------------------------------------------------------
def file_size(path: str | Path) -> int:
    """Return size in bytes, or 0 if the file doesn't exist."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0
