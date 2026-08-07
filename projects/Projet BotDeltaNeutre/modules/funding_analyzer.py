from __future__ import annotations
"""
modules/funding_analyzer.py - Funding rate analysis engine.
Computes moving averages, z-scores, annualized rates, and detects anomalies.
"""

import asyncio
import logging
import statistics
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

FUNDING_INTERVAL_HOURS = 1   # Pacifica: hourly funding, TWAP reset each hour
HOURS_PER_YEAR = 8760


class FundingSnapshot:
    __slots__ = ("timestamp", "pair", "rate", "next_funding_ts",
                 "open_interest", "volume_24h")

    def __init__(self, pair: str, rate: float, next_funding_ts: float = 0,
                 open_interest: float = 0, volume_24h: float = 0):
        self.timestamp = datetime.utcnow()
        self.pair = pair
        self.rate = rate
        self.next_funding_ts = next_funding_ts
        self.open_interest = open_interest
        self.volume_24h = volume_24h


class FundingAnalyzer:
    """
    Per-pair rolling funding analysis.
    Thread-safe, async-compatible.
    """

    def __init__(self, pair: str, ma_period: int = 24, config=None):
        self.pair = pair
        self.ma_period = ma_period
        self._config = config
        self._history: deque[float] = deque(maxlen=200)
        self._snapshots: deque[FundingSnapshot] = deque(maxlen=500)
        self._lock = asyncio.Lock()

    async def update(self, snapshot: FundingSnapshot):
        async with self._lock:
            self._history.append(snapshot.rate)
            self._snapshots.append(snapshot)

    @property
    def current_rate(self) -> float:
        return self._history[-1] if self._history else 0.0

    @property
    def moving_average(self) -> float:
        window = list(self._history)[-self.ma_period:]
        return statistics.mean(window) if len(window) >= 2 else 0.0

    @property
    def std_dev(self) -> float:
        window = list(self._history)[-self.ma_period:]
        return statistics.stdev(window) if len(window) >= 2 else 0.0

    @property
    def z_score(self) -> float:
        sd = self.std_dev
        if sd == 0:
            return 0.0
        return (self.current_rate - self.moving_average) / sd

    @property
    def annualized_rate(self) -> float:
        """Annualized return from funding (8h interval assumed)."""
        intervals_per_year = HOURS_PER_YEAR / FUNDING_INTERVAL_HOURS
        return self.current_rate * intervals_per_year

    @property
    def annualized_ma(self) -> float:
        intervals_per_year = HOURS_PER_YEAR / FUNDING_INTERVAL_HOURS
        return self.moving_average * intervals_per_year

    def is_signal(self, k: float = 1.5, min_rate: float = 0.0001) -> bool:
        """Return True if |funding| is anomalously high (entry signal).
        Works for both positive (short receives) and negative (long receives).
        """
        if len(self._history) < self.ma_period:
            return False
        abs_rate = abs(self.current_rate)
        # Condition minimale : le taux dépasse le seuil absolu
        if abs_rate < min_rate:
            return False
        # Si écart-type ≈ 0 (taux stable), le seuil absolu suffit
        if self.std_dev < 1e-6:
            return True
        # Sinon, vérifier aussi le z-score
        threshold = abs(self.moving_average) + k * self.std_dev
        return abs_rate > threshold

    def summary(self) -> dict:
        return {
            "pair": self.pair,
            "current_rate": round(self.current_rate, 8),
            "rate_pct": f"{self.current_rate * 100:.4f}%",
            "ma": round(self.moving_average, 8),
            "std": round(self.std_dev, 8),
            "z_score": round(self.z_score, 3),
            "annualized_pct": f"{self.annualized_rate * 100:.2f}%",
            "annualized_ma_pct": f"{self.annualized_ma * 100:.2f}%",
            "history_count": len(self._history),
        }

    def detect_anomaly(self, drop_threshold_pct: float = 0.50) -> Optional[str]:
        """
        Detect sudden funding drop.
        Returns alert string or None.
        """
        if len(self._history) < 3:
            return None
        prev = list(self._history)[-2]
        curr = self.current_rate
        if prev > 0 and (prev - curr) / prev > drop_threshold_pct:
            return (f"⚠️ {self.pair}: Funding dropped "
                    f"{(prev - curr)/prev*100:.1f}% "
                    f"({prev*100:.4f}% → {curr*100:.4f}%)")
        return None

    def funding_collected_usd(self, position_size_usd: float) -> float:
        """Estimated USD collected per funding interval for given notional."""
        return position_size_usd * self.current_rate


class FundingAnalyzerManager:
    """Manages FundingAnalyzer instances for all active pairs."""

    def __init__(self, pairs: list[str], ma_period: int = 24):
        self._analyzers: dict[str, FundingAnalyzer] = {
            p: FundingAnalyzer(p, ma_period) for p in pairs
        }
        self.ma_period = ma_period

    def get(self, pair: str) -> FundingAnalyzer:
        if pair not in self._analyzers:
            self._analyzers[pair] = FundingAnalyzer(pair, self.ma_period)
        return self._analyzers[pair]

    def all_summaries(self) -> list[dict]:
        return [a.summary() for a in self._analyzers.values()]

    def top_opportunities(self, k: float = 1.5, min_rate: float = 0.0001) -> list[str]:
        return [
            p for p, a in self._analyzers.items()
            if a.is_signal(k, min_rate)
        ]

    def check_anomalies(self, drop_threshold: float = 0.50) -> list[str]:
        alerts = []
        for a in self._analyzers.values():
            msg = a.detect_anomaly(drop_threshold)
            if msg:
                alerts.append(msg)
        return alerts
