from __future__ import annotations
"""
modules/position_manager.py - Tracks and manages all open positions.
Maintains real-time delta neutrality state.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SpotPosition:
    pair: str
    size: float = 0.0          # in base asset
    avg_price: float = 0.0
    current_price: float = 0.0

    @property
    def notional(self) -> float:
        return self.size * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.size * (self.current_price - self.avg_price)

    @property
    def delta(self) -> float:
        """Positive delta for long spot."""
        return self.size


@dataclass
class PerpPosition:
    pair: str
    size: float = 0.0          # in base asset (positive = long, negative = short)
    avg_price: float = 0.0
    current_price: float = 0.0
    leverage: float = 1.0
    liquidation_price: float = 0.0
    margin_used: float = 0.0
    funding_collected: float = 0.0

    @property
    def notional(self) -> float:
        return abs(self.size) * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.size * (self.current_price - self.avg_price)

    @property
    def delta(self) -> float:
        """Negative for short perp."""
        return self.size

    @property
    def margin_ratio(self) -> float:
        if self.notional == 0:
            return 1.0
        if self.margin_used == 0:
            return 1.0
        return self.margin_used / self.notional

    def near_liquidation(self, buffer_pct: float = 0.15) -> bool:
        if self.liquidation_price <= 0 or self.current_price <= 0:
            return False
        if self.size < 0:  # short
            pct_away = (self.liquidation_price - self.current_price) / self.current_price
        else:              # long
            pct_away = (self.current_price - self.liquidation_price) / self.current_price
        return 0 < pct_away < buffer_pct


@dataclass
class PairState:
    """Combined state for a single pair's delta-neutral position."""
    pair: str
    spot: SpotPosition = field(default_factory=lambda: SpotPosition(""))
    perp: PerpPosition = field(default_factory=lambda: PerpPosition(""))
    active: bool = False
    entry_capital: float = 0.0
    realized_pnl: float = 0.0

    def __post_init__(self):
        self.spot.pair = self.pair
        self.perp.pair = self.pair

    @property
    def net_delta(self) -> float:
        """Net delta = spot delta + perp delta. Target: ~0."""
        return self.spot.delta + self.perp.delta

    @property
    def delta_ratio(self) -> float:
        """Delta as fraction of spot size. Target: ~0."""
        if self.spot.size == 0:
            return 0.0
        return self.net_delta / self.spot.size

    @property
    def gross_exposure(self) -> float:
        return self.spot.notional + self.perp.notional

    @property
    def total_unrealized_pnl(self) -> float:
        return self.spot.unrealized_pnl + self.perp.unrealized_pnl

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.total_unrealized_pnl + self.perp.funding_collected

    @property
    def roi_pct(self) -> float:
        if self.entry_capital == 0:
            return 0.0
        return self.total_pnl / self.entry_capital * 100

    def needs_rebalance(self, threshold: float = 0.02) -> bool:
        return abs(self.delta_ratio) > threshold

    def summary(self) -> dict:
        return {
            "pair": self.pair,
            "active": self.active,
            "spot_size": round(self.spot.size, 6),
            "perp_size": round(self.perp.size, 6),
            "net_delta": round(self.net_delta, 6),
            "delta_ratio_pct": f"{self.delta_ratio * 100:.2f}%",
            "spot_notional": round(self.spot.notional, 2),
            "perp_notional": round(self.perp.notional, 2),
            "gross_exposure": round(self.gross_exposure, 2),
            "unrealized_pnl": round(self.total_unrealized_pnl, 4),
            "funding_collected": round(self.perp.funding_collected, 4),
            "total_pnl": round(self.total_pnl, 4),
            "roi_pct": f"{self.roi_pct:.3f}%",
            "near_liquidation": self.perp.near_liquidation(),
        }


class PositionManager:
    """Manages all pair states. Thread-safe via asyncio.Lock."""

    def __init__(self):
        self._pairs: dict[str, PairState] = {}
        self._lock = asyncio.Lock()
        self._total_realized_pnl: float = 0.0

    async def get_or_create(self, pair: str) -> PairState:
        async with self._lock:
            if pair not in self._pairs:
                self._pairs[pair] = PairState(pair=pair)
            return self._pairs[pair]

    async def update_prices(self, pair: str, spot_price: float, perp_price: float):
        async with self._lock:
            state = self._pairs.get(pair)
            if state:
                state.spot.current_price = spot_price
                state.perp.current_price = perp_price

    async def update_from_exchange(self, pair: str, spot_data: dict,
                                   perp_data: dict):
        """Sync position state from exchange API response."""
        async with self._lock:
            state = await self.get_or_create(pair)
            # Spot
            state.spot.size = float(spot_data.get("size", 0))
            state.spot.avg_price = float(spot_data.get("avg_price", 0))
            state.spot.current_price = float(spot_data.get("mark_price", 0))
            # Perp
            state.perp.size = float(perp_data.get("size", 0))
            state.perp.avg_price = float(perp_data.get("avg_price", 0))
            state.perp.current_price = float(perp_data.get("mark_price", 0))
            state.perp.liquidation_price = float(perp_data.get("liq_price", 0))
            state.perp.margin_used = float(perp_data.get("margin", 0))
            state.perp.funding_collected += float(perp_data.get("funding_delta", 0))

    async def record_funding(self, pair: str, amount_usd: float):
        async with self._lock:
            state = self._pairs.get(pair)
            if state:
                state.perp.funding_collected += amount_usd

    async def record_realized_pnl(self, pair: str, pnl: float):
        async with self._lock:
            state = self._pairs.get(pair)
            if state:
                state.realized_pnl += pnl
            self._total_realized_pnl += pnl

    async def all_summaries(self) -> list[dict]:
        async with self._lock:
            return [s.summary() for s in self._pairs.values()]

    async def total_pnl(self) -> float:
        async with self._lock:
            return sum(s.total_pnl for s in self._pairs.values())

    async def total_funding_collected(self) -> float:
        async with self._lock:
            return sum(s.perp.funding_collected for s in self._pairs.values())

    async def total_exposure(self) -> float:
        async with self._lock:
            return sum(s.gross_exposure for s in self._pairs.values())

    async def get_pairs_needing_rebalance(self, threshold: float) -> list[str]:
        async with self._lock:
            return [p for p, s in self._pairs.items()
                    if s.active and s.needs_rebalance(threshold)]

    async def get_liquidation_alerts(self, buffer_pct: float = 0.15) -> list[str]:
        async with self._lock:
            alerts = []
            for p, s in self._pairs.items():
                if s.active and s.perp.near_liquidation(buffer_pct):
                    lp = s.perp.liquidation_price
                    cp = s.perp.current_price
                    pct_away = abs(lp - cp) / cp * 100
                    alerts.append(
                        f"🚨 {p}: Liquidation price ${lp:.2f} "
                        f"({pct_away:.1f}% away from ${cp:.2f})"
                    )
            return alerts
