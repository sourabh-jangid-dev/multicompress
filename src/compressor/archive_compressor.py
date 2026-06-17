"""
archive_compressor.py
---------------------
For files we can't "smart-compress" (e.g. .docx, .exe, .txt, code folders),
we fall back to packing them into a .7z archive.

LIBRARY: py7zr
  Creates 7-Zip (.7z) archives. 7z uses the LZMA2 algorithm, which usually
  beats classic .zip on ratio — good for documents, source code, datasets.

NOTE (domain): already-compressed files (jpg, mp4, mp3, zip) won't shrink
much here, because their data is already packed. Archiving shines on text,
office docs, and folders of many small files.
"""

from __future__ import annotations

from pathlib import Path

import py7zr

from .presets import Preset
from .utils import build_output_path, file_size, human_size, reduction_percent


def compress_archive(input_path: str | Path, output_dir: str | Path,
                     preset: Preset) -> dict:
    input_path = Path(input_path)

    # For a folder, original size = sum of all files inside.
    if input_path.is_dir():
        original_bytes = sum(file_size(p) for p in input_path.rglob("*") if p.is_file())
    else:
        original_bytes = file_size(input_path)

    output_path = build_output_path(input_path, output_dir,
                                    suffix="", new_ext=".7z")

    # 'w' = create a new archive. py7zr streams files in, so even a huge
    # folder doesn't get loaded into RAM all at once.
    with py7zr.SevenZipFile(output_path, "w") as archive:
        if input_path.is_dir():
            # arcname keeps the folder name as the top entry inside the archive.
            archive.writeall(input_path, arcname=input_path.name)
        else:
            archive.write(input_path, arcname=input_path.name)

    compressed_bytes = file_size(output_path)

    return {
        "type": "archive",
        "input": str(input_path),
        "output": str(output_path),
        "original_bytes": original_bytes,
        "compressed_bytes": compressed_bytes,
        "original_human": human_size(original_bytes),
        "compressed_human": human_size(compressed_bytes),
        "saved_percent": round(reduction_percent(original_bytes, compressed_bytes), 1),
        "success": True,
    }
