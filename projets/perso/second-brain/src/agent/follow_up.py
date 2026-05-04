"""
Second Brain — Système de Suivi (Phase 4)
============================================
Vérifie les tâches en attente et génère des rappels.

Logique de suivi :
  - Jour 1 : pas de rappel (tâche vient d'être créée)
  - Jour 2 : rappel doux → "Tu n'as pas encore commencé..."
  - Jour 3+ : escalade → suggestion simplifiée

Chaque rappel incrémente le compteur de la tâche
pour éviter le spam et permettre l'escalade progressive.
"""

import logging
from datetime import datetime, timezone, timedelta

from config.settings import (
    FOLLOW_UP_REMINDER_HOURS,
    FOLLOW_UP_ESCALATION_HOURS,
)
from src.tasks import get_pending_tasks, update_task_reminder

logger = logging.getLogger(__name__)


# ── Reminder Levels ─────────────────────────────────────────────────

LEVEL_NONE = "none"         # Too recent, no reminder
LEVEL_REMINDER = "rappel"   # Gentle reminder
LEVEL_ESCALATION = "escalade"  # Escalated with simplified action


# ── Public API ──────────────────────────────────────────────────────

def check_follow_ups(tasks: list[dict] = None) -> list[dict]:
    """
    Vérifier les tâches en attente et générer des rappels.

    Scanne toutes les tâches pending/in_progress et détermine
    si un rappel ou une escalade est nécessaire.

    Args:
        tasks: Liste de tâches (charge depuis le fichier si non fourni).

    Returns:
        Liste de dicts de rappels :
        - task: la tâche concernée
        - message: texte du rappel
        - level: "rappel" | "escalade"
    """
    if tasks is None:
        tasks = get_pending_tasks()

    if not tasks:
        return []

    now = datetime.now(timezone.utc)
    reminders = []

    for task in tasks:
        level = _determine_level(task, now)

        if level == LEVEL_NONE:
            continue

        # Check if we already reminded recently (avoid spam within same cycle)
        if _was_reminded_recently(task, now, min_hours=12):
            continue

        message = _build_message(task, level)
        reminders.append({
            "task": task,
            "message": message,
            "level": level,
        })

        # Mark as reminded
        update_task_reminder(task["id"])

    if reminders:
        logger.info(
            f"Follow-up: {len(reminders)} reminders "
            f"({sum(1 for r in reminders if r['level'] == LEVEL_REMINDER)} rappels, "
            f"{sum(1 for r in reminders if r['level'] == LEVEL_ESCALATION)} escalades)"
        )

    return reminders


# ── Internal Logic ──────────────────────────────────────────────────

def _determine_level(task: dict, now: datetime) -> str:
    """
    Determine the reminder level for a task based on its age.

    Returns:
        LEVEL_NONE, LEVEL_REMINDER, or LEVEL_ESCALATION.
    """
    created_str = task.get("created_at", "")
    if not created_str:
        return LEVEL_NONE

    try:
        created = datetime.fromisoformat(created_str)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return LEVEL_NONE

    hours_since_creation = (now - created).total_seconds() / 3600.0

    if hours_since_creation >= FOLLOW_UP_ESCALATION_HOURS:
        return LEVEL_ESCALATION
    elif hours_since_creation >= FOLLOW_UP_REMINDER_HOURS:
        return LEVEL_REMINDER
    else:
        return LEVEL_NONE


def _was_reminded_recently(
    task: dict,
    now: datetime,
    min_hours: float = 12,
) -> bool:
    """Check if the task was reminded within the last min_hours."""
    last_str = task.get("last_reminded_at")
    if not last_str:
        return False

    try:
        last = datetime.fromisoformat(last_str)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        hours_since = (now - last).total_seconds() / 3600.0
        return hours_since < min_hours
    except (ValueError, TypeError):
        return False


def _build_message(task: dict, level: str) -> str:
    """
    Build the reminder message based on level.

    Args:
        task:  The task dict.
        level: LEVEL_REMINDER or LEVEL_ESCALATION.

    Returns:
        Human-readable reminder message in French.
    """
    title = task.get("title", "Tâche sans titre")
    steps = task.get("steps", [])
    reminder_count = task.get("reminder_count", 0)

    if level == LEVEL_REMINDER:
        # Gentle reminder
        msg = f"📋 Rappel : tu n'as pas encore commencé « {title} »."
        if steps:
            msg += f" Commence par l'étape 1 : {steps[0]}"
        return msg

    elif level == LEVEL_ESCALATION:
        # Escalated — suggest the simplest next action
        if steps:
            # Suggest just the first step, simplified
            simple_step = steps[0]
            msg = (
                f"⚠️ « {title} » attend depuis plus de 2 jours. "
                f"Action simplifiée : {simple_step}"
            )
        else:
            msg = (
                f"⚠️ « {title} » attend depuis plus de 2 jours. "
                f"Consacre 15 minutes à cette tâche aujourd'hui."
            )

        if reminder_count >= 3:
            msg += " (rappel répété — envisage de reprioritiser)"

        return msg

    return ""
