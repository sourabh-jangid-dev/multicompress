"""
history.py
----------
Keeps a running log of every file compressed, so we can show lifetime stats
like "You've saved 4.2 GB across 137 files". Great portfolio detail — shows
you think about data, not just features.

STORAGE: ~/.multicompress/history.json  (a JSON list of records)

TEACHING NOTE — we keep the log small by storing only what we need
(sizes + names + time), never the file contents.
"""

from __future__ import annotations

import json
from datetime import datetime

from .config import APP_DIR

HISTORY_FILE = APP_DIR / "history.json"


def add_record(result: dict) -> None:
    """Append one compression result to the history log."""
    records = load_history()
    records.append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "name": result.get("input", ""),
        "type": result.get("type", ""),
        "original_bytes": result.get("original_bytes", 0),
        "compressed_bytes": result.get("compressed_bytes", 0),
        "saved_percent": result.get("saved_percent", 0),
        "success": result.get("success", False),
    })
    APP_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")


def load_history() -> list[dict]:
    """Return the full history list (empty if none yet)."""
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def lifetime_stats() -> dict:
    """Aggregate totals across all history for a dashboard line."""
    records = load_history()
    before = sum(r["original_bytes"] for r in records)
    after = sum(r["compressed_bytes"] for r in records)
    return {
        "files": len(records),
        "saved_bytes": max(0, before - after),
        "total_before": before,
        "total_after": after,
    }
