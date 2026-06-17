"""
audio_compressor.py
-------------------
Compresses audio files (mp3, wav, m4a, flac, ...) by re-encoding them to MP3
at the preset's bitrate. A 50 MB WAV can drop to a few MB as MP3 with no
audible difference for most listeners.

DOMAIN NOTE:
  WAV/FLAC are uncompressed/lossless -> huge. Converting to MP3/AAC at
  128-192 kbps is "lossy" but transparent for speech and most music.
  Already-MP3 files at a higher bitrate also shrink when re-encoded lower.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from .ffmpeg_runner import get_ffmpeg, probe_duration, run_ffmpeg
from .presets import Preset
from .utils import build_output_path, file_size, human_size, reduction_percent, safe_copy


def compress_audio(input_path: str | Path, output_dir: str | Path,
                   preset: Preset,
                   progress_callback: Callable[[float], None] | None = None,
                   cancel_event: threading.Event | None = None) -> dict:
    input_path = Path(input_path)
    original_bytes = file_size(input_path)
    output_path = build_output_path(input_path, output_dir, new_ext=".mp3")

    cmd = [
        get_ffmpeg(), "-y",
        "-i", str(input_path),
        "-c:a", "libmp3lame",            # MP3 encoder
        "-b:a", f"{preset.audio_bitrate}k",
        "-map", "a",                     # take only audio streams (ignore cover art etc.)
        str(output_path),
    ]

    returncode, cancelled = run_ffmpeg(cmd, progress_callback, cancel_event)

    if cancelled:
        try:
            Path(output_path).unlink(missing_ok=True)
        except OSError:
            pass
        return _report(input_path, "", original_bytes, 0, False, cancelled=True)

    success = returncode == 0
    compressed_bytes = file_size(output_path) if success else 0

    if not success or (compressed_bytes >= original_bytes and original_bytes > 0):
        if original_bytes > 0:
            safe_copy(input_path, output_path)
            compressed_bytes = original_bytes
            success = True

    return _report(input_path, output_path, original_bytes, compressed_bytes, success)


def compress_audio_to_size(input_path: str | Path, output_dir: str | Path,
                           target_bytes: int,
                           progress_callback: Callable[[float], None] | None = None,
                           cancel_event: threading.Event | None = None) -> dict:
    """TARGET-SIZE mode for audio: bitrate = target_bits / duration."""
    input_path = Path(input_path)
    original_bytes = file_size(input_path)
    output_path = build_output_path(input_path, output_dir, new_ext=".mp3")

    duration = probe_duration(str(input_path))
    if duration <= 0:
        from .presets import get_preset
        return compress_audio(input_path, output_dir, get_preset("small"),
                              progress_callback, cancel_event)

    # MP3 needs a sane floor/ceiling; clamp to the standard 32..320 kbps range.
    kbps = int((target_bytes * 8 / 1000) / duration * 0.98)
    kbps = max(32, min(320, kbps))

    cmd = [get_ffmpeg(), "-y", "-i", str(input_path),
           "-c:a", "libmp3lame", "-b:a", f"{kbps}k", "-map", "a",
           str(output_path)]
    returncode, cancelled = run_ffmpeg(cmd, progress_callback, cancel_event)

    if cancelled:
        try:
            Path(output_path).unlink(missing_ok=True)
        except OSError:
            pass
        return _report(input_path, "", original_bytes, 0, False, cancelled=True)

    success = returncode == 0
    compressed_bytes = file_size(output_path) if success else 0
    if not success and original_bytes > 0:
        safe_copy(input_path, output_path)
        compressed_bytes = original_bytes
        success = True
    return _report(input_path, output_path, original_bytes, compressed_bytes, success)


def _report(input_path, output_path, original_bytes, compressed_bytes,
            success: bool, cancelled: bool = False) -> dict:
    return {
        "type": "audio",
        "input": str(input_path),
        "output": str(output_path),
        "original_bytes": original_bytes,
        "compressed_bytes": compressed_bytes,
        "original_human": human_size(original_bytes),
        "compressed_human": human_size(compressed_bytes),
        "saved_percent": round(reduction_percent(original_bytes, compressed_bytes), 1),
        "success": success,
        "cancelled": cancelled,
    }
