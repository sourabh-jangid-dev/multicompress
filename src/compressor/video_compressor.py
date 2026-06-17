"""
video_compressor.py
-------------------
Compresses a video with FFmpeg (via the shared ffmpeg_runner), streaming it
through disk (never into RAM), reporting LIVE progress, and supporting cancel.

THE COMMAND (and what each flag means):
  ffmpeg -y -i INPUT
    -vf scale=-2:'min(ih,720)'   # cap height; -2 keeps width even (H.264 needs even dims)
    -c:v libx264                 # H.264 codec (universal compatibility)
    -crf 28                      # quality dial: lower=better/bigger
    -preset medium               # encode speed/efficiency trade-off
    -c:a aac -b:a 128k           # AAC audio at the preset's bitrate
    -movflags +faststart         # index at front -> instant web playback
    OUTPUT.mp4
"""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from .ffmpeg_runner import get_ffmpeg, probe_duration, run_ffmpeg
from .presets import Preset
from .utils import build_output_path, file_size, human_size, reduction_percent, safe_copy


def compress_video(input_path: str | Path, output_dir: str | Path,
                   preset: Preset,
                   progress_callback: Callable[[float], None] | None = None,
                   cancel_event: threading.Event | None = None) -> dict:
    input_path = Path(input_path)
    original_bytes = file_size(input_path)
    output_path = build_output_path(input_path, output_dir, new_ext=".mp4")

    cmd = [
        get_ffmpeg(), "-y",
        "-i", str(input_path),
        "-vf", f"scale=-2:'min(ih,{preset.video_max_height})'",
        "-c:v", "libx264",
        "-crf", str(preset.video_crf),
        "-preset", "medium",
        "-c:a", "aac", "-b:a", f"{preset.audio_bitrate}k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    returncode, cancelled = run_ffmpeg(cmd, progress_callback, cancel_event)

    if cancelled:
        # Clean up the half-written file and report cancellation.
        try:
            Path(output_path).unlink(missing_ok=True)
        except OSError:
            pass
        return _report(input_path, "", original_bytes, 0,
                       success=False, cancelled=True)

    success = returncode == 0
    compressed_bytes = file_size(output_path) if success else 0

    # Safety net: failed OR result bigger -> keep the original.
    if not success or (compressed_bytes >= original_bytes and original_bytes > 0):
        if original_bytes > 0:
            safe_copy(input_path, output_path)
            compressed_bytes = original_bytes
            success = True

    return _report(input_path, output_path, original_bytes, compressed_bytes, success)


def compress_video_to_size(input_path: str | Path, output_dir: str | Path,
                           target_bytes: int, audio_bitrate: int = 128,
                           progress_callback: Callable[[float], None] | None = None,
                           cancel_event: threading.Event | None = None) -> dict:
    """
    TARGET-SIZE mode: encode the video to land under `target_bytes`.

    THE MATH (teaching):
      total_bits = target_bytes * 8
      video_bitrate = total_bits / duration_seconds  -  audio_bitrate

    We try precise TWO-PASS first, but fall back to a robust SINGLE-PASS
    average-bitrate encode if two-pass fails for any reason (it relies on a
    temp log file + a chained process, which can be fragile). If everything
    fails we report an HONEST error instead of silently keeping the original.
    """
    input_path = Path(input_path)
    original_bytes = file_size(input_path)
    output_path = build_output_path(input_path, output_dir, new_ext=".mp4")

    # GUARD: never grow a file. If it's already under the target, keep it.
    if 0 < original_bytes <= target_bytes:
        safe_copy(input_path, output_path)
        if progress_callback:
            progress_callback(100.0)
        return _report(input_path, output_path, original_bytes, original_bytes,
                       True, note="already under target")

    duration = probe_duration(str(input_path))
    if duration <= 0:
        from .presets import get_preset
        return compress_video(input_path, output_dir, get_preset("small"),
                              progress_callback, cancel_event)

    # Reserve ~3% headroom for container overhead so we stay UNDER the target.
    total_kbits = (target_bytes * 8 / 1000) * 0.97
    video_kbps = max(80, int(total_kbits / duration) - audio_bitrate)
    ff = get_ffmpeg()

    def fits(p):
        return p and Path(p).exists() and 0 < file_size(p) <= target_bytes * 1.10

    # --- Attempt 1: precise two-pass --------------------------------------
    cancelled = _two_pass(ff, input_path, output_path, video_kbps, audio_bitrate,
                          progress_callback, cancel_event)
    if cancelled:
        _safe_unlink(output_path)
        return _report(input_path, "", original_bytes, 0, False, cancelled=True)

    # --- Attempt 2: robust single-pass ABR (if two-pass missed/failed) -----
    if not fits(output_path):
        cancelled = _single_pass(ff, input_path, output_path, video_kbps,
                                 audio_bitrate, progress_callback, cancel_event)
        if cancelled:
            _safe_unlink(output_path)
            return _report(input_path, "", original_bytes, 0, False, cancelled=True)

    # --- Evaluate result --------------------------------------------------
    out_bytes = file_size(output_path)
    if out_bytes <= 0:
        # Both encodes failed -> honest error (do NOT fake success).
        return _report(input_path, "", original_bytes, 0, False,
                       error="encode failed")
    if out_bytes >= original_bytes:
        # Somehow bigger -> keep the original instead.
        safe_copy(input_path, output_path)
        out_bytes = original_bytes
    return _report(input_path, output_path, original_bytes, out_bytes, True)


def _two_pass(ff, input_path, output_path, vkbps, abitrate, cb, cancel_event) -> bool:
    """Run two-pass encoding. Returns True if cancelled."""
    with tempfile.TemporaryDirectory() as tmp:
        passlog = str(Path(tmp) / "ff2pass")
        cmd1 = [ff, "-y", "-i", str(input_path),
                "-c:v", "libx264", "-b:v", f"{vkbps}k",
                "-pass", "1", "-passlogfile", passlog,
                "-an", "-f", "null", _null_target()]
        rc1, cancelled = run_ffmpeg(cmd1, lambda p: cb(p * 0.5) if cb else None, cancel_event)
        if cancelled:
            return True
        if rc1 != 0:
            return False  # let caller fall back to single-pass

        cmd2 = [ff, "-y", "-i", str(input_path),
                "-c:v", "libx264", "-b:v", f"{vkbps}k",
                "-pass", "2", "-passlogfile", passlog,
                "-c:a", "aac", "-b:a", f"{abitrate}k",
                "-movflags", "+faststart", str(output_path)]
        _rc2, cancelled = run_ffmpeg(cmd2, lambda p: cb(50 + p * 0.5) if cb else None,
                                     cancel_event)
        return cancelled


def _single_pass(ff, input_path, output_path, vkbps, abitrate, cb, cancel_event) -> bool:
    """
    Single-pass average-bitrate encode. Less precise than two-pass but very
    robust (no temp log, one process). maxrate/bufsize cap size spikes.
    Returns True if cancelled.
    """
    cmd = [ff, "-y", "-i", str(input_path),
           "-c:v", "libx264", "-b:v", f"{vkbps}k",
           "-maxrate", f"{int(vkbps * 1.3)}k", "-bufsize", f"{int(vkbps * 2)}k",
           "-preset", "medium",
           "-c:a", "aac", "-b:a", f"{abitrate}k",
           "-movflags", "+faststart", str(output_path)]
    _rc, cancelled = run_ffmpeg(cmd, cb, cancel_event)
    return cancelled


def _safe_unlink(path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _null_target() -> str:
    """FFmpeg's 'throw away the output' target differs per OS."""
    import sys
    return "NUL" if sys.platform.startswith("win") else "/dev/null"


def _report(input_path, output_path, original_bytes, compressed_bytes,
            success: bool, cancelled: bool = False,
            note: str = "", error: str = "") -> dict:
    return {
        "type": "video",
        "input": str(input_path),
        "output": str(output_path),
        "original_bytes": original_bytes,
        "compressed_bytes": compressed_bytes,
        "original_human": human_size(original_bytes),
        "compressed_human": human_size(compressed_bytes),
        "saved_percent": round(reduction_percent(original_bytes, compressed_bytes), 1),
        "success": success,
        "cancelled": cancelled,
        "note": note,
        "error": error,
    }
