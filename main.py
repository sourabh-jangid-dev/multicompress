"""
main.py — the program's entry point.
Run the app with:  python main.py

This file does two small jobs:
  1. Make the `src/` folder importable (so `import compressor...` works).
  2. Launch the GUI.

Keeping the entry point tiny is good practice — all real logic lives in the
packages under src/, which keeps things testable and reusable (a CLI could
import the exact same engine).
"""

import sys
from pathlib import Path

# Add the src/ directory to Python's import path.
SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))

from gui.app import run  # noqa: E402  (import after sys.path tweak — intentional)

if __name__ == "__main__":
    # Any paths passed on the command line (e.g. from the Windows right-click
    # "Compress with MultiCompress" menu) are pre-loaded into the queue.
    run(initial_files=sys.argv[1:])
