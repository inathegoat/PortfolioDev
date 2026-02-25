"""
core/config.py - Dynamic configuration manager
Supports hot-reload of strategy params without restart.
"""

import json
import threading
from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class Config:
    """Thread-safe dynamic configuration with hot-reload support."""

    def __init__(self, config_path: str = "config.json"):
        self._path = Path(config_path)
        self._lock = threading.RLock()
        self._data: dict = {}
        self._dirty_keys: list = []  # [(keys_tuple, value), ...]
        self.load()

    def load(self):
        with self._lock:
            with open(self._path, "r") as f:
                self._data = json.load(f)
            self._dirty_keys.clear()
        logger.info(f"Config loaded from {self._path}")

    def save(self):
        """Sauvegarde en fusionnant les changements programmatiques
        avec le fichier sur disque, pour ne pas écraser les modifs manuelles."""
        with self._lock:
            if not self._dirty_keys:
                return  # Rien à sauvegarder

            # Relire le fichier depuis le disque
            try:
                with open(self._path, "r") as f:
                    disk_data = json.load(f)
            except Exception:
                disk_data = {}

            # Appliquer uniquement les clés modifiées par le bot
            for keys, value in self._dirty_keys:
                node = disk_data
                for k in keys[:-1]:
                    node = node.setdefault(k, {})
                node[keys[-1]] = value

            # Écrire le résultat fusionné
            with open(self._path, "w") as f:
                json.dump(disk_data, f, indent=2)

            # Synchroniser la mémoire avec le disque
            self._data = disk_data
            self._dirty_keys.clear()
        logger.info("Config saved to disk")

    def get(self, *keys: str, default=None) -> Any:
        with self._lock:
            node = self._data
            for k in keys:
                if isinstance(node, dict) and k in node:
                    node = node[k]
                else:
                    return default
            return node

    def set(self, *keys_and_value) -> None:
        """set('strategy', 'max_leverage', 3.0) - last arg is value."""
        keys = keys_and_value[:-1]
        value = keys_and_value[-1]
        with self._lock:
            node = self._data
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
            self._dirty_keys.append((keys, value))
        self.save()

    # ── Shortcuts ──────────────────────────────────────────────────────────
    @property
    def strategy(self) -> dict:
        return self.get("strategy") or {}

    @property
    def risk(self) -> dict:
        return self.get("risk") or {}

    @property
    def telegram(self) -> dict:
        return self.get("telegram") or {}

    @property
    def pacifica(self) -> dict:
        return self.get("pacifica") or {}


# Singleton
_config_instance: Optional[Config] = None


def get_config(path: str = "config.json") -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(path)
    return _config_instance
