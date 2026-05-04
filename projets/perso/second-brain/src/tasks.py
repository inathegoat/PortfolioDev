"""
Second Brain — Système de Tâches (Phase 4)
=============================================
Gère les tâches générées par le système d'insights.

Chaque tâche est liée à un objectif et contient des étapes
concrètes. Le système de suivi utilise les champs
last_reminded_at et reminder_count pour les rappels.

Stockage : tasks/tasks.json
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import TASKS_FILE, TASKS_DIR

logger = logging.getLogger(__name__)


# ── Public API ──────────────────────────────────────────────────────

def load_tasks() -> list[dict]:
    """
    Charger toutes les tâches depuis le fichier JSON.

    Returns:
        Liste de dicts de tâches.
    """
    _ensure_file_exists()

    try:
        content = TASKS_FILE.read_text(encoding="utf-8")
        data = json.loads(content)

        if not isinstance(data, list):
            logger.warning("Tasks file is not a list, returning empty")
            return []

        return data

    except json.JSONDecodeError:
        logger.warning("Tasks file is corrupted, returning empty")
        return []
    except Exception as e:
        logger.error(f"Failed to load tasks: {e}")
        return []


def save_tasks(tasks: list[dict]) -> None:
    """
    Sauvegarder les tâches dans le fichier JSON.

    Args:
        tasks: Liste de dicts de tâches à persister.
    """
    _ensure_file_exists()

    try:
        TASKS_FILE.write_text(
            json.dumps(tasks, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Saved {len(tasks)} tasks")
    except Exception as e:
        logger.error(f"Failed to save tasks: {e}")

def delete_task(task_id: str) -> bool:
    """
    Delete a task by ID.
    """
    tasks = load_tasks()
    initial_len = len(tasks)
    tasks = [t for t in tasks if t.get("id") != task_id]
    
    if len(tasks) < initial_len:
        save_tasks(tasks)
        logger.info(f"Deleted task: {task_id}")
        return True
    return False


def add_task(
    goal_id: str,
    title: str,
    description: str = "",
    steps: list[str] = None,
    priority: int = 5,
    due_date: Optional[str] = None,
) -> dict:
    """
    Ajouter une nouvelle tâche.

    Args:
        goal_id:     ID de l'objectif associé.
        title:       Titre court de la tâche.
        description: Description détaillée.
        steps:       Sous-étapes concrètes.
        priority:    Priorité 1-10.
        due_date:    Date limite optionnelle (ISO format).

    Returns:
        Le dict de la tâche créée.
    """
    task_id = f"task_{uuid.uuid4().hex[:8]}"

    task = {
        "id": task_id,
        "goal_id": goal_id,
        "title": title,
        "description": description,
        "steps": steps or [],
        "status": "pending",
        "priority": max(1, min(10, priority)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "due_date": due_date,
        "last_reminded_at": None,
        "reminder_count": 0,
    }

    tasks = load_tasks()
    tasks.append(task)
    save_tasks(tasks)

    logger.info(f"Added task: {title} (priority={priority}, goal={goal_id})")
    return task


def update_task_status(task_id: str, status: str) -> bool:
    """
    Mettre à jour le statut d'une tâche.

    Args:
        task_id: Identifiant de la tâche.
        status:  Nouveau statut (pending / in_progress / done).

    Returns:
        True si mis à jour, False si non trouvé.
    """
    valid_statuses = {"pending", "in_progress", "done"}
    if status not in valid_statuses:
        logger.warning(f"Invalid status: {status}. Must be one of {valid_statuses}")
        return False

    tasks = load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = status
            if status == "done":
                task["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks(tasks)
            logger.info(f"Task '{task_id}' → {status}")
            return True

    logger.warning(f"Task not found: {task_id}")
    return False


def update_task_reminder(task_id: str) -> bool:
    """
    Marquer qu'un rappel a été envoyé pour cette tâche.

    Incrémente reminder_count et met à jour last_reminded_at.

    Returns:
        True si mis à jour, False si non trouvé.
    """
    tasks = load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            task["reminder_count"] = task.get("reminder_count", 0) + 1
            task["last_reminded_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks(tasks)
            return True
    return False


def get_pending_tasks() -> list[dict]:
    """Retourner toutes les tâches en attente ou en cours."""
    tasks = load_tasks()
    return [
        t for t in tasks
        if t.get("status") in ("pending", "in_progress")
    ]


def get_tasks_for_goal(goal_id: str) -> list[dict]:
    """Retourner toutes les tâches liées à un objectif."""
    tasks = load_tasks()
    return [t for t in tasks if t.get("goal_id") == goal_id]


def get_task(task_id: str) -> Optional[dict]:
    """Retourner une tâche par son ID."""
    tasks = load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def task_exists_similar(title: str, threshold: float = 0.6) -> bool:
    """
    Vérifier si une tâche similaire existe déjà.

    Compare les titres en minuscules. Si plus de `threshold`
    des mots du nouveau titre existent dans un titre existant,
    on considère que c'est un doublon.

    Args:
        title:     Titre de la nouvelle tâche.
        threshold: Seuil de similarité (0.0 à 1.0).

    Returns:
        True si un doublon probable existe.
    """
    tasks = load_tasks()
    if not tasks or not title:
        return False

    new_words = set(title.lower().split())
    if not new_words:
        return False

    for task in tasks:
        if task.get("status") == "done":
            continue  # Ignore completed tasks

        existing_words = set(task.get("title", "").lower().split())
        if not existing_words:
            continue

        # Jaccard-like similarity
        overlap = len(new_words & existing_words)
        similarity = overlap / max(len(new_words), len(existing_words))

        if similarity >= threshold:
            logger.debug(
                f"Duplicate task detected: '{title}' ≈ '{task['title']}' "
                f"(similarity={similarity:.2f})"
            )
            return True

    return False


# ── Private Helpers ─────────────────────────────────────────────────

def _ensure_file_exists() -> None:
    """Créer le répertoire et le fichier si nécessaire."""
    TASKS_DIR.mkdir(parents=True, exist_ok=True)

    if not TASKS_FILE.exists():
        TASKS_FILE.write_text("[]", encoding="utf-8")
        logger.info(f"Created tasks file: {TASKS_FILE}")
