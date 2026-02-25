"""
modules/risk_manager.py - Contrôles de risque et circuit breakers.
"""

import asyncio
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


class RiskViolation(Exception):
    pass


class RiskManager:
    """
    Applique les limites de risque. Tous les contrôles sont async-compatibles.
    L'état du circuit breaker est maintenu en mémoire.
    """

    def __init__(self, config):
        self._cfg = config
        self._circuit_open: bool = False
        self._circuit_reason: str = ""
        self._daily_loss: float = 0.0
        self._daily_reset_date: date = datetime.utcnow().date()
        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0
        self._lock = asyncio.Lock()

    # ── Mise à jour de l'état ────────────────────────────────────────────────

    async def update_equity(self, equity: float):
        async with self._lock:
            self._reset_daily_if_needed()
            if equity < self._current_equity:
                loss = self._current_equity - equity
                self._daily_loss += loss
            self._current_equity = equity
            if equity > self._peak_equity:
                self._peak_equity = equity

    def _reset_daily_if_needed(self):
        today = datetime.utcnow().date()
        if today != self._daily_reset_date:
            self._daily_loss = 0.0
            self._daily_reset_date = today
            logger.info("Compteur de perte journalière réinitialisé")

    # ── Vérifications ────────────────────────────────────────────────────────

    async def check_all(self, equity: float) -> list[str]:
        """Retourne la liste des règles déclenchées. Vide = tout OK."""
        await self.update_equity(equity)
        violations = []
        r = self._cfg.risk

        # Drawdown maximum
        if self._peak_equity > 0:
            dd = (self._peak_equity - equity) / self._peak_equity
            if dd > r.get("max_drawdown_pct", 0.10):
                violations.append(
                    f"MAX_DRAWDOWN: {dd*100:.2f}% > "
                    f"{r['max_drawdown_pct']*100:.1f}%"
                )

        # Perte journalière
        if self._current_equity > 0:
            daily_pct = self._daily_loss / self._current_equity
            if daily_pct > r.get("max_daily_loss_pct", 0.03):
                violations.append(
                    f"PERTE_JOUR: {daily_pct*100:.2f}% > "
                    f"{r['max_daily_loss_pct']*100:.1f}%"
                )

        return violations

    async def check_leverage(self, requested: float) -> float:
        """Limiter le levier au maximum autorisé."""
        max_lev = self._cfg.risk.get("max_leverage_hard", 5.0)
        if requested > max_lev:
            logger.warning(f"Levier {requested}x limité à {max_lev}x")
            return max_lev
        return requested

    async def check_concentration(self, pair_capital: float,
                                  total_capital: float, pair: str) -> bool:
        max_pct = self._cfg.risk.get("max_concentration_per_pair_pct", 0.5)
        if total_capital <= 0:
            return True
        ratio = pair_capital / total_capital
        if ratio > max_pct:
            logger.warning(f"Concentration {pair}: {ratio*100:.1f}% > {max_pct*100:.1f}%")
            return False
        return True

    async def check_order_size(self, size_usd: float,
                               min_size: float = 50.0) -> bool:
        return size_usd >= min_size

    async def check_global_leverage(self, total_exposure: float,
                                     total_capital: float,
                                     max_leverage: float = 5.0) -> bool:
        """
        Vérifie que le levier global ne dépasse pas le seuil autorisé.
        Retourne True si OK, False si levier excessif.
        """
        if total_capital <= 0:
            return False
        current_lev = total_exposure / total_capital
        if current_lev > max_leverage:
            logger.warning(
                f"Levier global {current_lev:.1f}x dépasse le max {max_leverage:.1f}x"
            )
            return False
        return True

    # ── Circuit Breaker ──────────────────────────────────────────────────────

    async def trip_circuit_breaker(self, reason: str):
        async with self._lock:
            if not self._circuit_open:
                self._circuit_open = True
                self._circuit_reason = reason
                logger.critical(f"CIRCUIT BREAKER DÉCLENCHÉ : {reason}")

    async def reset_circuit_breaker(self):
        async with self._lock:
            self._circuit_open = False
            self._circuit_reason = ""
            logger.warning("Circuit breaker RÉINITIALISÉ par l'opérateur")

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    @property
    def circuit_reason(self) -> str:
        return self._circuit_reason

    # ── Vérification automatique ─────────────────────────────────────────────

    async def auto_check_and_trip(self, equity: float) -> Optional[str]:
        """
        Exécute le contrôle de risque complet et déclenche le circuit breaker
        si des violations sont détectées. Retourne le message ou None.
        """
        if not self._cfg.risk.get("circuit_breaker_enabled", True):
            return None

        violations = await self.check_all(equity)
        if violations:
            reason = "; ".join(violations)
            await self.trip_circuit_breaker(reason)
            return reason
        return None

    # ── Statut ───────────────────────────────────────────────────────────────

    def status(self) -> dict:
        dd = 0.0
        if self._peak_equity > 0:
            dd = (self._peak_equity - self._current_equity) / self._peak_equity
        return {
            "circuit_open": self._circuit_open,
            "circuit_reason": self._circuit_reason,
            "current_equity": round(self._current_equity, 2),
            "peak_equity": round(self._peak_equity, 2),
            "drawdown_pct": f"{dd * 100:.2f}%",
            "daily_loss_usd": round(self._daily_loss, 2),
            "daily_reset": str(self._daily_reset_date),
        }
