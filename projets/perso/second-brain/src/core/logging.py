"""src/core/logging.py — Centralized structured logging.

Supports plain text and JSON formats.
"""
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = str(record.exc_info[1])
        extra = getattr(record, "extra", None)
        if extra and isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    name: str = "second-brain",
    level: int = logging.INFO,
    log_file: str = "logs/second_brain.log",
    json_format: bool = False,
) -> logging.Logger:
    """Configure and return the root logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        # File handler
        fh = logging.FileHandler(log_file)
        fh.setFormatter(JSONFormatter() if json_format else logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(fh)

        # Console handler (always plain text)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(ch)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger."""
    return logging.getLogger(f"second-brain.{name}")
