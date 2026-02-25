"""
wallet/wallet_manager.py - Gestionnaire de portefeuille interne.
Suivi du capital, allocation par paire, funding cumulé, persistance JSON.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WalletManager:
    """
    Portefeuille interne du bot.
    Gère le capital total, disponible, engagé, funding accumulé,
    PnL réalisé/non réalisé, et l'allocation par paire.
    Persiste l'état dans un fichier JSON pour survivre aux redémarrages.
    """

    def __init__(self, state_file: str = "data/wallet_state.json",
                 initial_capital: float = 10000.0):
        self._state_file = Path(state_file)
        self._lock = asyncio.Lock()

        # Valeurs par défaut
        self.initial_capital: float = initial_capital
        self.total_capital: float = initial_capital
        self.available_capital: float = initial_capital
        self.committed_capital: float = 0.0
        self.accumulated_funding: float = 0.0
        self.realized_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0
        self._allocations: dict[str, float] = {}
        self._history: list[dict] = []

        # Charger l'état persisté s'il existe
        self._load()

    # ── Gestion du capital ──────────────────────────────────────────────────

    async def set_capital(self, amount: float):
        """Définir le capital initial et réinitialiser le portefeuille."""
        async with self._lock:
            self.initial_capital = amount
            self.total_capital = amount + self.accumulated_funding + self.realized_pnl
            self.available_capital = self.total_capital - self.committed_capital
            self._add_history("set_capital", amount)
            self._save()

    async def add_funds(self, amount: float):
        """Ajouter des fonds au portefeuille."""
        async with self._lock:
            self.total_capital += amount
            self.available_capital += amount
            self.initial_capital += amount
            self._add_history("add_funds", amount)
            self._save()

    async def remove_funds(self, amount: float) -> bool:
        """Retirer des fonds du portefeuille. Retourne False si insuffisant."""
        async with self._lock:
            if amount > self.available_capital:
                return False
            self.total_capital -= amount
            self.available_capital -= amount
            self.initial_capital -= amount
            self._add_history("remove_funds", -amount)
            self._save()
            return True

    # ── Allocation par paire ────────────────────────────────────────────────

    def can_allocate(self, amount: float) -> bool:
        """Vérifier si le capital disponible est suffisant."""
        return amount <= self.available_capital

    async def allocate(self, pair: str, amount: float) -> bool:
        """
        Réserver du capital pour une paire.
        Retourne False si capital insuffisant.
        """
        async with self._lock:
            if amount > self.available_capital:
                return False
            self.available_capital -= amount
            self.committed_capital += amount
            self._allocations[pair] = self._allocations.get(pair, 0.0) + amount
            self._add_history("allocate", amount, pair=pair)
            self._save()
            return True

    async def release(self, pair: str, pnl: float = 0.0):
        """Libérer le capital d'une paire avec le PnL réalisé."""
        async with self._lock:
            allocated = self._allocations.pop(pair, 0.0)
            self.committed_capital -= allocated
            self.realized_pnl += pnl
            returned = allocated + pnl
            self.available_capital += returned
            self.total_capital += pnl
            self._add_history("release", returned, pair=pair, pnl=pnl)
            self._save()

    async def record_funding(self, pair: str, amount: float):
        """Enregistrer le funding collecté."""
        async with self._lock:
            self.accumulated_funding += amount
            self.total_capital += amount
            self.available_capital += amount
            self._save()

    # ── Vérifications Risk ──────────────────────────────────────────────────

    def check_leverage(self, total_exposure: float, max_leverage: float) -> bool:
        """Vérifie que le levier global ne dépasse pas le seuil."""
        if self.total_capital <= 0:
            return False
        current_leverage = total_exposure / self.total_capital
        return current_leverage <= max_leverage

    def check_max_allocation(self, amount: float, max_pct: float) -> bool:
        """Vérifie que l'allocation ne dépasse pas le maximum autorisé."""
        if self.total_capital <= 0:
            return False
        return (amount / self.total_capital) <= max_pct

    # ── Calculs ─────────────────────────────────────────────────────────────

    @property
    def total_pnl(self) -> float:
        """PnL total = réalisé + non réalisé + funding."""
        return self.realized_pnl + self.unrealized_pnl + self.accumulated_funding

    @property
    def roi_pct(self) -> float:
        """ROI en pourcentage par rapport au capital initial."""
        if self.initial_capital <= 0:
            return 0.0
        return self.total_pnl / self.initial_capital * 100

    def get_allocation(self, pair: str) -> float:
        """Capital alloué à une paire spécifique."""
        return self._allocations.get(pair, 0.0)

    @property
    def allocations(self) -> dict[str, float]:
        """Copie des allocations par paire."""
        return dict(self._allocations)

    def get_average_leverage(self, total_exposure: float) -> float:
        """Calculer le levier moyen."""
        if self.total_capital <= 0:
            return 0.0
        return total_exposure / self.total_capital

    # ── Snapshot pour dashboard ─────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Retourne un dictionnaire de l'état complet du portefeuille."""
        return {
            "initial_capital": round(self.initial_capital, 2),
            "total_capital": round(self.total_capital, 2),
            "available_capital": round(self.available_capital, 2),
            "committed_capital": round(self.committed_capital, 2),
            "accumulated_funding": round(self.accumulated_funding, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "total_pnl": round(self.total_pnl, 4),
            "roi_pct": round(self.roi_pct, 2),
            "allocations": dict(self._allocations),
            "num_allocations": len(self._allocations),
        }

    async def update_unrealized_pnl(self, unrealized: float):
        """Mettre à jour le PnL non réalisé (depuis les positions ouvertes)."""
        async with self._lock:
            self.unrealized_pnl = unrealized

    # ── Historique ──────────────────────────────────────────────────────────

    def _add_history(self, action: str, amount: float, **extra):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "amount": round(amount, 4),
            "total_capital": round(self.total_capital, 2),
            "available": round(self.available_capital, 2),
            "committed": round(self.committed_capital, 2),
        }
        entry.update(extra)
        self._history.append(entry)
        # Garder les 500 dernières entrées
        if len(self._history) > 500:
            self._history = self._history[-500:]

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    # ── Persistance ─────────────────────────────────────────────────────────

    def _save(self):
        """Sauvegarder l'état dans un fichier JSON."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "initial_capital": self.initial_capital,
                "total_capital": self.total_capital,
                "available_capital": self.available_capital,
                "committed_capital": self.committed_capital,
                "accumulated_funding": self.accumulated_funding,
                "realized_pnl": self.realized_pnl,
                "unrealized_pnl": self.unrealized_pnl,
                "allocations": self._allocations,
                "history": self._history[-100:],  # Garder les 100 dernières
                "last_saved": datetime.utcnow().isoformat(),
            }
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde wallet : {e}")

    def _load(self):
        """Charger l'état depuis le fichier JSON s'il existe."""
        if not self._state_file.exists():
            logger.info("Aucun état wallet trouvé, utilisation des valeurs par défaut")
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.initial_capital = state.get("initial_capital", self.initial_capital)
            self.total_capital = state.get("total_capital", self.total_capital)
            self.available_capital = state.get("available_capital", self.available_capital)
            self.committed_capital = state.get("committed_capital", self.committed_capital)
            self.accumulated_funding = state.get("accumulated_funding", 0.0)
            self.realized_pnl = state.get("realized_pnl", 0.0)
            self.unrealized_pnl = state.get("unrealized_pnl", 0.0)
            self._allocations = state.get("allocations", {})
            self._history = state.get("history", [])
            logger.info(f"État wallet chargé : capital={self.total_capital:.2f}, "
                        f"disponible={self.available_capital:.2f}")
        except Exception as e:
            logger.error(f"Erreur chargement wallet : {e}")
