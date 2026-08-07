"""
localization/translator.py - Module de traduction.
Charge les fichiers de langue JSON et fournit une interface t(key, **kwargs).
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Translator:
    """
    Gestionnaire de traduction.
    Charge un fichier JSON de langue et permet l'interpolation de variables.
    """

    def __init__(self, lang: str = "fr"):
        self._lang = lang
        self._strings: dict = {}
        self._load(lang)

    def _load(self, lang: str):
        """Charge le fichier de langue depuis lang/{lang}.json."""
        lang_file = Path(__file__).parent.parent / "lang" / f"{lang}.json"
        if not lang_file.exists():
            logger.error(f"Fichier de langue introuvable : {lang_file}")
            return
        with open(lang_file, "r", encoding="utf-8") as f:
            self._strings = json.load(f)
        logger.info(f"Langue '{lang}' chargée ({lang_file})")

    def t(self, key: str, **kwargs) -> str:
        """
        Obtenir une traduction par clé avec interpolation.

        Exemples :
            t("bot.started")
            t("wallet.capital_total", amount=10000)
            t("dashboard.statut", status="🟢 Actif")

        Args:
            key: Clé en notation pointée (ex: "bot.started")
            **kwargs: Variables à interpoler dans le template

        Returns:
            La chaîne traduite, ou la clé si non trouvée.
        """
        parts = key.split(".")
        node = self._strings
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                logger.warning(f"Clé de traduction manquante : {key}")
                return key

        if not isinstance(node, str):
            return key

        if kwargs:
            try:
                return node.format(**kwargs)
            except (KeyError, ValueError, IndexError) as e:
                logger.warning(f"Erreur d'interpolation pour '{key}': {e}")
                return node
        return node

    @property
    def lang(self) -> str:
        return self._lang


# Singleton
_translator_instance: Optional[Translator] = None


def get_translator(lang: str = "fr") -> Translator:
    """Obtenir l'instance singleton du traducteur."""
    global _translator_instance
    if _translator_instance is None or _translator_instance.lang != lang:
        _translator_instance = Translator(lang)
    return _translator_instance
