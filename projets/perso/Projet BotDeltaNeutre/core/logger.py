from __future__ import annotations
"""
core/logger.py - Structured logging with rotation and CSV export hooks.
"""

import logging
import logging.handlers
import csv
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logging(log_dir: str = "logs", level: str = "INFO", console: bool = True):
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    fh = logging.handlers.TimedRotatingFileHandler(
        log_path / "bot.log", when="midnight", backupCount=7, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


class TradeLogger:
    """CSV-based trade history logger."""

    FIELDS = [
        "timestamp", "pair", "side", "market_type", "qty", "price",
        "fee", "pnl", "funding_collected", "delta_after", "notes"
    ]

    def __init__(self, export_dir: str = "data"):
        self._dir = Path(export_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self) -> Path:
        return self._dir / f"trades_{datetime.utcnow().strftime('%Y%m')}.csv"

    def log_trade(self, **kwargs):
        path = self._path()
        write_header = not path.exists()
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            if write_header:
                writer.writeheader()
            row = {k: kwargs.get(k, "") for k in self.FIELDS}
            row["timestamp"] = row["timestamp"] or datetime.utcnow().isoformat()
            writer.writerow(row)


class FundingLogger:
    """CSV logger for funding fees collected."""

    FIELDS = ["timestamp", "pair", "rate", "interval_hours",
              "position_size", "funding_usd", "cumulative_usd"]

    def __init__(self, export_dir: str = "data"):
        self._dir = Path(export_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cumulative: dict[str, float] = {}

    def _path(self) -> Path:
        return self._dir / f"funding_{datetime.utcnow().strftime('%Y%m')}.csv"

    def log_funding(self, pair: str, rate: float, interval_hours: float,
                    position_size: float, funding_usd: float):
        self._cumulative[pair] = self._cumulative.get(pair, 0.0) + funding_usd
        path = self._path()
        write_header = not path.exists()
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.utcnow().isoformat(),
                "pair": pair,
                "rate": rate,
                "interval_hours": interval_hours,
                "position_size": position_size,
                "funding_usd": funding_usd,
                "cumulative_usd": self._cumulative[pair],
            })
