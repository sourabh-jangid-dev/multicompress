"""
cli.py — command-line version of the compressor.

Same engine as the GUI, no window. Great for power users, scripts, and to
demonstrate that our architecture is REUSABLE (GUI and CLI share 100% of the
compression logic).

USAGE:
    python cli.py video.mp4 photo.jpg scan.pdf
    python cli.py *.png --preset small --output ./out
    python cli.py bigvideo.mov -p high_quality

Run `python cli.py --help` for all options.
"""

import argparse
import sys
from pathlib import Path

# Make src/ importable, exactly like main.py does.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from compressor.engine import compress_path, detect_kind  # noqa: E402
from compressor.presets import DEFAULT_PRESET, PRESETS  # noqa: E402
from compressor.utils import human_size  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Compress videos, images, audio, PDFs and files — 100% offline.")
    parser.add_argument("files", nargs="+", help="One or more files/folders to compress.")
    parser.add_argument("-p", "--preset", default=DEFAULT_PRESET,
                        choices=list(PRESETS.keys()),
                        help=f"Compression preset (default: {DEFAULT_PRESET}).")
    parser.add_argument("-o", "--output", default="compressed_output",
                        help="Output folder (default: ./compressed_output).")
    args = parser.parse_args()

    total_before = total_after = 0
    print(f"Preset: {PRESETS[args.preset].name}  →  Output: {args.output}\n")

    for f in args.files:
        if not Path(f).exists():
            print(f"  ⚠ skip (not found): {f}")
            continue

        kind = detect_kind(f)
        print(f"  [{kind:7}] {Path(f).name} … ", end="", flush=True)

        # Simple inline progress for videos/audio.
        # Bind f/kind as defaults so the closure captures THIS iteration's values
        # (not the loop variable's final value) — the classic late-binding gotcha.
        def cb(pct, f=f, kind=kind):
            print(f"\r  [{kind:7}] {Path(f).name} … {pct:5.1f}%", end="", flush=True)

        r = compress_path(f, args.output, args.preset, cb)
        total_before += r["original_bytes"]
        total_after += r["compressed_bytes"]

        if r["success"]:
            print(f"\r  [{kind:7}] {Path(f).name} … "
                  f"{r['original_human']} → {r['compressed_human']} "
                  f"(-{r['saved_percent']}%)        ")
        else:
            print(f"\r  [{kind:7}] {Path(f).name} … FAILED: {r.get('error','')}    ")

    saved = total_before - total_after
    pct = (saved / total_before * 100) if total_before else 0
    print(f"\nTotal saved: {human_size(saved)} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
