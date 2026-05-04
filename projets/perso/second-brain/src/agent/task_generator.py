"""
Second Brain — Générateur de Tâches (Phase 4)
================================================
Convertit les insights en tâches structurées avec sous-étapes.

Pipeline :
1. Prend les insights générés par le système d'attention
2. Utilise le LLM pour structurer chaque insight en tâche
3. Associe chaque tâche à l'objectif le plus pertinent
4. Vérifie les doublons avant d'ajouter
5. Génère des sous-étapes via le moteur de planification
"""

import logging
import re

from src.ai.llm_client import LLMClient
from src.goals import match_goals, load_goals
from src.tasks import add_task, task_exists_similar, load_tasks
from src.planner import generate_plan
from config.settings import TASK_PRIORITY_THRESHOLD

logger = logging.getLogger(__name__)


# ── Prompts ─────────────────────────────────────────────────────────

TASK_SYSTEM_PROMPT = """Tu es un système de gestion de tâches. Tu convertis des insights en tâches structurées.

Règles :
1. Pour chaque insight, génère UN titre de tâche court (max 10 mots).
2. Génère une description en 1-2 phrases.
3. Format STRICT pour chaque tâche :
   TITRE: [titre de la tâche]
   DESCRIPTION: [description courte]
4. Sépare chaque tâche par une ligne vide.
5. Réponds TOUJOURS en français.
"""

TASK_PROMPT_TEMPLATE = """Convertis ces insights en tâches concrètes et actionnables.

=== INSIGHTS ===
{insights_text}

=== OBJECTIFS DE L'UTILISATEUR ===
{goals_text}

Pour chaque insight, génère une tâche avec :
- TITRE: un titre court et actionnable (commence par un verbe)
- DESCRIPTION: une description en 1-2 phrases

Retourne les tâches au format demandé.
"""


# ── Public API ──────────────────────────────────────────────────────

def generate_tasks(
    insights: list[str],
    goals: list[dict] = None,
    ranked_memories: list[dict] = None,
    llm: LLMClient = None,
) -> list[dict]:
    """
    Convertir des insights en tâches structurées.

    Pipeline :
    1. Appeler le LLM pour structurer les insights en tâches
    2. Associer chaque tâche à un objectif
    3. Filtrer les doublons
    4. Générer des sous-étapes
    5. Sauvegarder les nouvelles tâches

    Args:
        insights:        Liste d'insights (strings).
        goals:           Objectifs utilisateur.
        ranked_memories: Mémoires classées (pour le contexte du planner).
        llm:             Client LLM.

    Returns:
        Liste des tâches créées (dicts).
    """
    if not insights:
        return []

    if goals is None:
        goals = load_goals()

    if llm is None:
        llm = LLMClient()

    # ── Step 1: Convert insights to task structures ─────────────────
    raw_tasks = _insights_to_raw_tasks(insights, goals, llm)

    if not raw_tasks:
        logger.info("No tasks generated from insights")
        return []

    # ── Step 2: Filter duplicates and create tasks ──────────────────
    created = []
    for raw in raw_tasks:
        title = raw.get("title", "")
        description = raw.get("description", "")
        goal_id = raw.get("goal_id", "")
        priority = raw.get("priority", 5)

        # Skip low priority
        if priority < TASK_PRIORITY_THRESHOLD:
            logger.debug(f"Skipping low-priority task: {title} (p={priority})")
            continue

        # Skip duplicates
        if task_exists_similar(title):
            logger.info(f"Skipping duplicate task: {title}")
            continue

        # ── Step 3: Generate sub-steps ──────────────────────────────
        goal = _find_goal(goal_id, goals)
        steps = generate_plan(
            task_title=title,
            task_description=description,
            goal=goal,
            context_memories=ranked_memories,
            llm=llm,
        )

        # ── Step 4: Save the task ───────────────────────────────────
        task = add_task(
            goal_id=goal_id,
            title=title,
            description=description,
            steps=steps,
            priority=priority,
        )
        created.append(task)
        logger.info(
            f"✅ Task created: {title} ({len(steps)} steps, p={priority})"
        )

    logger.info(f"Created {len(created)} tasks from {len(insights)} insights")
    return created


# ── Internal Logic ──────────────────────────────────────────────────

def _insights_to_raw_tasks(
    insights: list[str],
    goals: list[dict],
    llm: LLMClient,
) -> list[dict]:
    """
    Use the LLM to convert insights into raw task structures.

    Returns list of dicts with title, description, goal_id, priority.
    """
    # Build prompt
    insights_text = "\n".join(
        f"{i+1}. {insight}" for i, insight in enumerate(insights)
    )
    goals_text = "\n".join(
        f"- [{g.get('priority', 5)}/10] {g.get('title', '')} "
        f"(ID: {g.get('id', '')})"
        for g in goals
    )

    prompt = TASK_PROMPT_TEMPLATE.format(
        insights_text=insights_text,
        goals_text=goals_text,
    )

    try:
        raw_response = llm.generate(
            prompt=prompt,
            system_prompt=TASK_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=600,
        )
        return _parse_tasks(raw_response, insights, goals)

    except ConnectionError:
        logger.error("Cannot connect to Ollama for task generation")
        return _fallback_tasks(insights, goals)
    except Exception as e:
        logger.error(f"Task generation failed: {e}")
        return _fallback_tasks(insights, goals)


def _parse_tasks(
    raw_text: str,
    insights: list[str],
    goals: list[dict],
) -> list[dict]:
    """Parse LLM response into task structures."""
    if not raw_text:
        return _fallback_tasks(insights, goals)

    tasks = []
    current_title = None
    current_description = None

    for line in raw_text.strip().split("\n"):
        line = line.strip()
        if not line:
            # Save previous task if exists
            if current_title:
                task = _build_task_dict(
                    current_title, current_description or "", goals
                )
                tasks.append(task)
                current_title = None
                current_description = None
            continue

        # Match TITRE: or TITLE:
        title_match = re.match(
            r"^(?:TITRE|TITLE|Titre)\s*:\s*(.+)", line, re.IGNORECASE
        )
        if title_match:
            # Save previous task
            if current_title:
                task = _build_task_dict(
                    current_title, current_description or "", goals
                )
                tasks.append(task)
            current_title = title_match.group(1).strip()
            current_description = None
            continue

        # Match DESCRIPTION:
        desc_match = re.match(
            r"^(?:DESCRIPTION|Description)\s*:\s*(.+)", line, re.IGNORECASE
        )
        if desc_match:
            current_description = desc_match.group(1).strip()
            continue

    # Don't forget the last task
    if current_title:
        task = _build_task_dict(
            current_title, current_description or "", goals
        )
        tasks.append(task)

    if not tasks:
        return _fallback_tasks(insights, goals)

    return tasks


def _build_task_dict(
    title: str,
    description: str,
    goals: list[dict],
) -> dict:
    """Build a task dict with goal matching and priority."""
    # Match to best goal
    text = f"{title} {description}"
    goal_matches = match_goals(text, goals)

    if goal_matches:
        best_goal = goal_matches[0]["goal"]
        goal_id = best_goal.get("id", "")
        # Priority = average of goal priority and match strength
        goal_priority = best_goal.get("priority", 5)
        priority = min(10, max(1, (goal_priority + 5) // 2 + 2))
    else:
        goal_id = ""
        priority = 5

    return {
        "title": title,
        "description": description,
        "goal_id": goal_id,
        "priority": priority,
    }


def _fallback_tasks(
    insights: list[str],
    goals: list[dict],
) -> list[dict]:
    """
    Create basic task structures from insights without LLM.

    Used when Ollama is unavailable.
    """
    tasks = []
    for insight in insights[:3]:  # Limit to 3
        # Use insight as both title and description
        title = insight[:80] if len(insight) > 80 else insight
        task = _build_task_dict(title, insight, goals)
        tasks.append(task)
    return tasks


def _find_goal(goal_id: str, goals: list[dict]) -> dict:
    """Find a goal by ID."""
    if not goal_id:
        return None
    for goal in goals:
        if goal.get("id") == goal_id:
            return goal
    return None
