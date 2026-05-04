"""src/agents_v2/briefing.py — Daily briefing generator.

Generates a morning/on-demand summary:
- Pending tasks with priorities
- Active goals with progress
- Recently ingested documents
- Suggested actions (max 3)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Briefing:
    """Daily briefing for the user."""
    date: str = ""
    tasks_pending: List[Dict] = field(default_factory=list)
    tasks_due_soon: List[Dict] = field(default_factory=list)
    goals_active: List[Dict] = field(default_factory=list)
    recent_documents: List[str] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)
    profile: str = ""


class BriefingGenerator:
    """Generates daily briefings from tasks, goals, documents, and profile."""

    def __init__(
        self,
        llm_client=None,
        profile_manager=None,
    ):
        self.llm = llm_client
        self.profile = profile_manager

    def generate(self, max_suggestions: int = 3) -> Briefing:
        """Generate a full daily briefing."""
        from src.tasks import load_tasks
        from src.goals import load_goals
        from src.memory.vector_store import VectorStore
        from config.settings import RAW_DIR

        today = datetime.now().strftime("%Y-%m-%d")

        # Tasks
        tasks = load_tasks()
        pending = [t for t in tasks if t.get("status") in ("pending", "in_progress")]
        pending.sort(key=lambda t: t.get("priority", 5), reverse=True)
        due_soon = [
            t for t in pending
            if t.get("due_date") and t["due_date"] <= datetime.now().strftime("%Y-%m-%d")
        ]

        # Goals
        goals = load_goals()
        active_goals = [
            g for g in goals
            if g.get("progress", 0) < 100
        ]
        active_goals.sort(key=lambda g: g.get("priority", 5), reverse=True)

        # Documents
        vs = VectorStore()
        sources = vs.list_sources()
        recent_docs = sources[:10] if len(sources) > 10 else sources

        # Profile
        profile_text = ""
        if self.profile:
            profile_text = self.profile.format_for_prompt()

        # Suggested actions (LLM generated, max 3)
        suggestions = self._generate_suggestions(
            pending, active_goals, recent_docs, profile_text, max_suggestions
        )

        return Briefing(
            date=today,
            tasks_pending=pending[:5],
            tasks_due_soon=due_soon[:3],
            goals_active=active_goals[:5],
            recent_documents=recent_docs[:5],
            suggested_actions=suggestions,
            profile=profile_text,
        )

    def _generate_suggestions(
        self,
        tasks: List[Dict],
        goals: List[Dict],
        docs: List[str],
        profile: str,
        max_n: int = 3,
    ) -> List[str]:
        """Use LLM to generate 3 concrete suggested actions."""
        if not self.llm or not self.llm.is_available():
            return self._rule_based_suggestions(tasks, goals)

        tasks_text = "\n".join(
            f"- [{t.get('priority', '?')}] {t.get('title', '')} (status: {t.get('status', '')})"
            for t in tasks[:5]
        ) or "Aucune tâche en cours."

        goals_text = "\n".join(
            f"- {g.get('title', '')} (progrès: {g.get('progress', 0)}%)"
            for g in goals[:5]
        ) or "Aucun objectif actif."

        docs_text = ", ".join(docs[:5]) if docs else "Aucun document récent."

        prompt = (
            f"Profil : {profile or 'Non configuré.'}\n\n"
            f"Tâches en cours :\n{tasks_text}\n\n"
            f"Objectifs actifs :\n{goals_text}\n\n"
            f"Documents récents : {docs_text}\n\n"
            f"Propose exactement {max_n} actions concrètes que l'utilisateur "
            f"devrait faire aujourd'hui. Sois bref et actionnable. "
            f"Une action par ligne, précédée d'un tiret."
        )

        try:
            raw = self.llm.generate(
                prompt=prompt,
                system_prompt=(
                    "Tu es un assistant personnel qui suggère des actions concrètes. "
                    "Propose uniquement des actions basées sur les informations fournies. "
                    "Maximum 3 suggestions. Format : - Action concrète"
                ),
                temperature=0.3,
                max_tokens=300,
            )
            # Parse bullet points
            suggestions = []
            for line in raw.split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("*") or line.startswith("•"):
                    text = line.lstrip("-*• ").strip()
                    if text and len(text) > 10:
                        suggestions.append(text)
            return suggestions[:max_n]
        except Exception as e:
            logger.warning(f"LLM suggestions failed: {e}")
            return self._rule_based_suggestions(tasks, goals)

    def _rule_based_suggestions(self, tasks: List[Dict], goals: List[Dict]) -> List[str]:
        """Fallback: rule-based suggestions when LLM is unavailable."""
        suggestions = []
        for t in tasks[:3]:
            if t.get("priority", 5) >= 7:
                suggestions.append(f"Priorité haute : {t.get('title', 'Tâche sans titre')}")
        for g in goals[:2]:
            if g.get("progress", 100) < 50:
                suggestions.append(f"Avancer sur : {g.get('title', 'Objectif')} ({g.get('progress', 0)}%)")
        return suggestions[:3] if suggestions else [
            "Ingérer de nouveaux documents dans le Second Brain.",
            "Mettre à jour vos objectifs et priorités.",
            "Poser une question à votre base de connaissances.",
        ]

    def format_briefing(self, briefing: Briefing) -> str:
        """Format a briefing as readable text."""
        lines = [
            "=" * 50,
            f"  Second Brain — Briefing du {briefing.date}",
            "=" * 50,
            "",
        ]
        if briefing.profile:
            lines.append(f"Profil : {briefing.profile}")
            lines.append("")

        if briefing.tasks_due_soon:
            lines.append("🔴 TÂCHES URGENTES :")
            for t in briefing.tasks_due_soon:
                lines.append(f"  ⚠️  {t.get('title', '')} (priorité {t.get('priority', '?')})")
            lines.append("")

        if briefing.tasks_pending:
            lines.append("📋 TÂCHES EN COURS :")
            for t in briefing.tasks_pending:
                lines.append(f"  [{t.get('priority', '?')}] {t.get('title', '')} — {t.get('status', '')}")
            lines.append("")

        if briefing.goals_active:
            lines.append("🎯 OBJECTIFS ACTIFS :")
            for g in briefing.goals_active:
                lines.append(f"  {g.get('title', '')} ({g.get('progress', 0)}%)")
            lines.append("")

        if briefing.recent_documents:
            lines.append("📄 DOCUMENTS RÉCENTS :")
            for d in briefing.recent_documents:
                lines.append(f"  • {d}")
            lines.append("")

        if briefing.suggested_actions:
            lines.append("💡 SUGGESTIONS DU JOUR :")
            for i, s in enumerate(briefing.suggested_actions, 1):
                lines.append(f"  {i}. {s}")
            lines.append("")

        lines.append("=" * 50)
        return "\n".join(lines)
