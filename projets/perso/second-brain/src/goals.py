"""
Second Brain — Goal System (Phase 3)
======================================
Manages user goals and performs goal-memory matching.

Goals are stored in goals/goals.json and define what matters
to the user. The attention system uses goals to prioritize memories.

Each goal has:
  - id:          Unique identifier
  - title:       Short goal name
  - description: What the goal is about
  - priority:    Importance (1–10)
  - keywords:    Terms used for memory matching
  - progress:    Completion percentage (0–100)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from config.settings import GOALS_FILE, GOALS_DIR

logger = logging.getLogger(__name__)


# ── Public API ──────────────────────────────────────────────────────

def load_goals() -> list[dict]:
    """
    Load all goals from the JSON file.

    Creates the file with an empty list if it doesn't exist.

    Returns:
        List of goal dicts.
    """
    _ensure_file_exists()

    try:
        content = GOALS_FILE.read_text(encoding="utf-8")
        data = json.loads(content)

        if not isinstance(data, list):
            logger.warning("Goals file is not a list, returning empty")
            return []

        return data

    except json.JSONDecodeError:
        logger.warning("Goals file is corrupted, returning empty")
        return []
    except Exception as e:
        logger.error(f"Failed to load goals: {e}")
        return []


def save_goals(goals: list[dict]) -> None:
    """
    Save goals to the JSON file.

    Args:
        goals: List of goal dicts to persist.
    """
    _ensure_file_exists()

    try:
        GOALS_FILE.write_text(
            json.dumps(goals, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Saved {len(goals)} goals")
    except Exception as e:
        logger.error(f"Failed to save goals: {e}")


def get_goal(goal_id: str) -> Optional[dict]:
    """
    Get a single goal by ID.

    Args:
        goal_id: The goal's unique identifier.

    Returns:
        The goal dict, or None if not found.
    """
    goals = load_goals()
    for goal in goals:
        if goal.get("id") == goal_id:
            return goal
    return None


def update_progress(goal_id: str, progress: int) -> bool:
    """
    Update a goal's progress percentage.

    Args:
        goal_id:  The goal's unique identifier.
        progress: New progress value (0–100).

    Returns:
        True if updated, False if goal not found.
    """
    goals = load_goals()
    for goal in goals:
        if goal.get("id") == goal_id:
            goal["progress"] = max(0, min(100, progress))
            save_goals(goals)
            logger.info(f"Goal '{goal_id}' progress → {goal['progress']}%")
            return True
    logger.warning(f"Goal not found: {goal_id}")
    return False

def delete_goal(goal_id: str) -> bool:
    """
    Delete a goal by ID.
    
    Args:
        goal_id: The goal's unique identifier.
        
    Returns:
        True if deleted, False if not found.
    """
    goals = load_goals()
    initial_len = len(goals)
    goals = [g for g in goals if g.get("id") != goal_id]
    
    if len(goals) < initial_len:
        save_goals(goals)
        logger.info(f"Deleted goal: {goal_id}")
        return True
    return False


def add_goal(
    goal_id: str,
    title: str,
    description: str = "",
    priority: int = 5,
    keywords: list[str] = None,
) -> dict:
    """
    Add a new goal.

    Args:
        goal_id:     Unique identifier.
        title:       Short goal name.
        description: What the goal is about.
        priority:    Importance 1–10.
        keywords:    List of matching keywords.

    Returns:
        The created goal dict.
    """
    goal = {
        "id": goal_id,
        "title": title,
        "description": description,
        "priority": max(1, min(10, priority)),
        "keywords": keywords or [],
        "progress": 0,
    }

    goals = load_goals()
    goals.append(goal)
    save_goals(goals)

    logger.info(f"Added goal: {title} (priority={priority})")
    return goal


# ── Goal Matching (Task 3) ──────────────────────────────────────────

def match_goals(text: str, goals: list[dict] = None) -> list[dict]:
    """
    Match a text against user goals using keyword matching.

    Performs case-insensitive keyword search. Returns goals
    sorted by match strength (number of matched keywords × priority).

    Args:
        text:  The text to match (e.g., a memory's question + answer).
        goals: Optional list of goals (loads from file if not provided).

    Returns:
        List of dicts with:
        - goal: the matched goal
        - matched_keywords: list of keywords found
        - match_score: number of matches × goal priority
    """
    if goals is None:
        goals = load_goals()

    if not goals or not text:
        return []

    text_lower = text.lower()
    matches = []

    for goal in goals:
        keywords = goal.get("keywords", [])
        matched = [kw for kw in keywords if kw.lower() in text_lower]

        if matched:
            match_score = len(matched) * goal.get("priority", 5)
            matches.append({
                "goal": goal,
                "matched_keywords": matched,
                "match_score": match_score,
            })

    # Sort by match_score descending
    matches.sort(key=lambda m: m["match_score"], reverse=True)
    return matches


# ── Private Helpers ─────────────────────────────────────────────────

def _ensure_file_exists() -> None:
    """Create the goals directory and file if they don't exist."""
    GOALS_DIR.mkdir(parents=True, exist_ok=True)

    if not GOALS_FILE.exists():
        GOALS_FILE.write_text("[]", encoding="utf-8")
        logger.info(f"Created goals file: {GOALS_FILE}")
