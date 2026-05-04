"""src/memory/conversation.py — Mémoire conversationnelle SQLite."""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import CONV_DB, MAX_HISTORY_MESSAGES

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Persistance SQLite des échanges utilisateur/assistant."""

    def __init__(self, db_path: Path = CONV_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT    NOT NULL,
                    role       TEXT    NOT NULL,
                    content    TEXT    NOT NULL,
                    created_at TEXT    NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id)")
            conn.commit()

    # ── Écriture ─────────────────────────────────────────────────────

    def add_message(self, role: str, content: str, session_id: str = "default"):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
                (session_id, role, content, datetime.now().isoformat()),
            )
            conn.commit()

    # ── Lecture ──────────────────────────────────────────────────────

    def get_history(
        self,
        session_id: str = "default",
        limit: int = MAX_HISTORY_MESSAGES,
    ) -> List[Dict[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_ollama_messages(self, session_id: str = "default") -> List[Dict[str, str]]:
        """Format compatible Ollama /api/chat."""
        return self.get_history(session_id)

    def list_sessions(self) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT session_id FROM messages ORDER BY session_id"
            ).fetchall()
        return [r[0] for r in rows]

    def clear_session(self, session_id: str = "default"):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.commit()

    def count(self, session_id: Optional[str] = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            if session_id:
                return conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
