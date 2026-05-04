"""src/memory/user_profile.py — User preferences, subjects, and profile.

Stores:
- Personal info: name, language, response style
- Subjects: what the user is studying/working on
- Preferences: tone, verbosity, focus areas
- Long-term goals: linked to goals.py
"""
import logging
import sqlite3
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import DB_DIR

logger = logging.getLogger(__name__)

PROFILE_DB = DB_DIR / "profile.db"


@dataclass
class UserProfile:
    name: str = ""
    language: str = "fr"
    response_style: str = "concis"       # concis, détaillé, pédagogique
    tone: str = "neutre"                 # neutre, motivant, formel
    subjects: List[str] = field(default_factory=list)
    focus_areas: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


class ProfileManager:
    """Manages user profile in SQLite."""

    def __init__(self):
        self._init_db()

    def _connect(self):
        return sqlite3.connect(PROFILE_DB)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS profile (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        # Seed defaults if empty
        defaults = {
            "name": "",
            "language": "fr",
            "response_style": "concis",
            "tone": "neutre",
            "subjects": "",
            "focus_areas": "",
        }
        for k, v in defaults.items():
            self._set_if_missing(k, v)

    def _set_if_missing(self, key: str, default: str):
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM profile WHERE key=?", (key,)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO profile (key, value, updated_at) VALUES (?,?,?)",
                    (key, default, datetime.now().isoformat()),
                )
                conn.commit()

    def get(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM profile WHERE key=?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO profile (key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?",
                (key, value, datetime.now().isoformat(), value, datetime.now().isoformat()),
            )
            conn.commit()

    def get_profile(self) -> UserProfile:
        """Load full profile."""
        all_data = {}
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM profile").fetchall()
            for k, v in rows:
                all_data[k] = v

        return UserProfile(
            name=all_data.get("name", ""),
            language=all_data.get("language", "fr"),
            response_style=all_data.get("response_style", "concis"),
            tone=all_data.get("tone", "neutre"),
            subjects=[s.strip() for s in all_data.get("subjects", "").split(",") if s.strip()],
            focus_areas=[s.strip() for s in all_data.get("focus_areas", "").split(",") if s.strip()],
            raw=all_data,
        )

    def update_profile(self, **kwargs):
        """Update multiple profile fields at once."""
        for key, value in kwargs.items():
            if isinstance(value, list):
                value = ", ".join(value)
            self.set(key, str(value))

    def set_subjects(self, subjects: List[str]):
        self.set("subjects", ", ".join(subjects))

    def add_subject(self, subject: str):
        profile = self.get_profile()
        if subject not in profile.subjects:
            profile.subjects.append(subject)
            self.set_subjects(profile.subjects)

    def format_for_prompt(self) -> str:
        """Format profile as a prompt-friendly string."""
        p = self.get_profile()
        parts = []
        if p.name:
            parts.append(f"Utilisateur : {p.name}")
        if p.subjects:
            parts.append(f"Matières étudiées : {', '.join(p.subjects)}")
        if p.focus_areas:
            parts.append(f"Centres d'intérêt : {', '.join(p.focus_areas)}")
        parts.append(f"Style de réponse souhaité : {p.response_style}")
        parts.append(f"Ton : {p.tone}")
        return "\n".join(parts) if parts else "Profil non configuré."
