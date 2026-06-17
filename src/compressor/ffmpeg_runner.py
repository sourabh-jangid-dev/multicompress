"""
ffmpeg_runner.py
----------------
Shared helper that RUNS an FFmpeg command, reports live progress, and can be
CANCELLED mid-way. Both the video and audio compressors use this, so the
progress-parsing + cancel logic lives in ONE place (DRY principle).

CANCELLATION (teaching):
  We pass a `threading.Event` called `cancel_event`. The GUI's Stop button
  calls `cancel_event.set()`. While reading FFmpeg's output we check
  `cancel_event.is_set()` and, if so, terminate the FFmpeg process. That's how
  you cleanly stop a long-running external program.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from collections.abc import Callable

import imageio_ffmpeg

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
_TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+\.\d+)")

# On Windows, launching a child console program (ffmpeg.exe) from our windowed
# GUI pops up a black console window every time. CREATE_NO_WINDOW suppresses it.
# It's 0 on macOS/Linux, where this isn't an issue.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0


def _hms_to_seconds(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def get_ffmpeg() -> str:
    """Path to the bundled FFmpeg binary (shipped with imageio-ffmpeg)."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration(input_path: str) -> float:
    """
    Return a media file's duration in SECONDS (0.0 if unknown).

    We run FFmpeg with no output and read the "Duration:" line it prints to
    stderr. This avoids needing a separate ffprobe binary (imageio-ffmpeg only
    ships ffmpeg). Needed for target-size math: bitrate = target_bits / seconds.
    """
    try:
        proc = subprocess.run(
            [get_ffmpeg(), "-i", str(input_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, creationflags=_NO_WINDOW,
        )
        m = _DURATION_RE.search(proc.stderr or "")
        if m:
            return _hms_to_seconds(*m.groups())
    except Exception:
        pass
    return 0.0


def run_ffmpeg(cmd: list[str],
               progress_callback: Callable[[float], None] | None = None,
               cancel_event: threading.Event | None = None) -> tuple[int, bool]:
    """
    Run an FFmpeg command list.

    Returns (returncode, cancelled).
      - returncode 0  -> success.
      - cancelled True -> user hit Stop; output is incomplete/should be discarded.
    """
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        creationflags=_NO_WINDOW,
    )

    total_seconds = 0.0
    cancelled = False

    for line in process.stderr:
        # Stop requested? Kill FFmpeg and bail out.
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            cancelled = True
            break

        if total_seconds == 0.0:
            d = _DURATION_RE.search(line)
            if d:
                total_seconds = _hms_to_seconds(*d.groups())

        t = _TIME_RE.search(line)
        if t and total_seconds > 0 and progress_callback:
            done = _hms_to_seconds(*t.groups())
            progress_callback(min(100.0, done / total_seconds * 100.0))

    process.wait()
    if not cancelled and progress_callback:
        progress_callback(100.0)

    return process.returncode, cancelled
