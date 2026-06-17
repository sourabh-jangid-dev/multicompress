"""
logsetup.py
-----------
Configures a rotating log file so we can debug crashes from real users.

WHERE: ~/.multicompress/app.log  (rotates at 1 MB, keeps 3 old files)

WHY ROTATING (teaching):
  A plain log file grows forever. RotatingFileHandler caps the size and keeps a
  few backups, so logs never eat the user's disk. Standard production practice.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import APP_DIR

_configured = False


def get_logger() -> logging.Logger:
    """Return the shared app logger, configuring it once on first call."""
    global _configured
    logger = logging.getLogger("multicompress")
    if _configured:
        return logger

    logger.setLevel(logging.INFO)
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            APP_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(message)s"))
        logger.addHandler(handler)
    except Exception:
        # If we can't open the log file (e.g. read-only home), don't crash —
        # just run without file logging.
        pass

    _configured = True
    return logger
