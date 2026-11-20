"""Logging setup for VibeFinder.

Call setup_logging() once at startup (app.py and evaluate.py do this).
Messages go to the console and to logs/vibefinder.log (the logs/ folder is
in .gitignore). Calling it twice does not duplicate lines.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DEFAULT_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "vibefinder.log"


def setup_logging(log_file: Path | str | None = None, level: int = logging.INFO) -> Path:
    """Send all 'vibefinder.*' logs to the console and a file. Returns the file path."""
    path = Path(log_file) if log_file else DEFAULT_LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("vibefinder")
    root.setLevel(level)
    root.propagate = False

    already_files = {getattr(h, "baseFilename", None) for h in root.handlers}
    formatter = logging.Formatter(LOG_FORMAT)

    if str(path.resolve()) not in already_files:
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if not any(type(h) is logging.StreamHandler for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    return path