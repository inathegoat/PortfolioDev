"""src/memory/history.py — Historique des échanges pour Jarvis."""
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from config.settings import HIST_DB


def _init_db():
    with sqlite3.connect(HIST_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                question   TEXT NOT NULL,
                answer     TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

_init_db()


def load_memory(limit: int = 50) -> List[Dict[str, Any]]:
    with sqlite3.connect(HIST_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def save_memory(question: str, answer: str):
    with sqlite3.connect(HIST_DB) as conn:
        conn.execute(
            "INSERT INTO history (question, answer, created_at) VALUES (?,?,?)",
            (question, answer, datetime.now().isoformat()),
        )
        conn.commit()


def add_interaction(question: str, answer: str):
    """Alias de save_memory — appelé par rag_pipeline, ui/app.py, ui/telegram_bot.py."""
    save_memory(question, answer)


def format_history_for_prompt(limit: int = 5) -> str:
    """Formate les N dernières interactions pour le prompt LLM."""
    rows = load_memory(limit=limit)
    if not rows:
        return ""
    lines = []
    for r in rows:
        lines.append(f"User: {r['question']}")
        lines.append(f"Assistant: {r['answer']}")
        lines.append("")
    return "\n".join(lines)


def clear_memory():
    """Vide tout l'historique (appelée par main.py cmd_reset)."""
    with sqlite3.connect(HIST_DB) as conn:
        conn.execute("DELETE FROM history")
        conn.commit()


def get_memory_stats() -> Dict[str, Any]:
    """Statistiques de l'historique (appelée par main.py cmd_stats)."""
    with sqlite3.connect(HIST_DB) as conn:
        count = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        first = conn.execute(
            "SELECT created_at FROM history ORDER BY id ASC LIMIT 1"
        ).fetchone()
        last = conn.execute(
            "SELECT created_at FROM history ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "total_interactions": count,
        "first_interaction": first[0] if first else "",
        "last_interaction": last[0] if last else "",
        "db_file": str(HIST_DB),
    }
