"""
config.py
---------
Remembers the user's choices between runs (last preset, output folder, theme)
so the app feels polished instead of resetting every launch.

WHERE IT'S STORED:
  A small JSON file in the user's home folder:  ~/.multicompress/settings.json
  Using the home folder (not the app folder) means settings survive even if the
  app is reinstalled or moved.
"""

from __future__ import annotations

import json
from pathlib import Path

# Folder that holds settings + history. Created on first use.
APP_DIR = Path.home() / ".multicompress"
SETTINGS_FILE = APP_DIR / "settings.json"

# Sensible defaults if no settings file exists yet.
DEFAULTS = {
    "preset": "balanced",
    "output_dir": str(Path.home() / "Compressed"),
    "theme": "dark",          # "dark" | "light"
}


def load_settings() -> dict:
    """Read settings.json, filling in any missing keys with defaults."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    # Merge: defaults first, then whatever the user saved overrides them.
    return {**DEFAULTS, **data}


def save_settings(settings: dict) -> None:
    """Write settings.json (creating the folder if needed)."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
