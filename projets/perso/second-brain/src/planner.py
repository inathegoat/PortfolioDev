"""
Second Brain — Moteur de Planification (Phase 4)
===================================================
Décompose un objectif en étapes concrètes et actionnables.

Utilise le LLM local pour générer un plan réaliste
à partir d'un objectif et du contexte des mémoires.
"""

import logging
import re

from src.ai.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ── Prompts ─────────────────────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """Tu es un planificateur expert qui décompose des objectifs en étapes concrètes.

Règles :
1. Chaque étape doit être une action CONCRÈTE et réalisable en 1-2 heures.
2. Limite-toi à 3-5 étapes maximum.
3. Sois spécifique — pas de conseil vague comme "étudier plus".
4. Chaque étape commence par un VERBE d'action.
5. Retourne UNIQUEMENT une liste numérotée d'étapes.
6. Réponds TOUJOURS en français.
"""

PLANNER_PROMPT_TEMPLATE = """Décompose cette tâche en étapes concrètes et actionnables.

=== TÂCHE ===
{task_title}

=== DESCRIPTION ===
{task_description}

=== CONTEXTE (mémoires récentes de l'utilisateur) ===
{context}

=== OBJECTIF ASSOCIÉ ===
{goal_info}

Génère 3 à 5 étapes concrètes pour accomplir cette tâche. Chaque étape doit être réalisable en 1-2 heures.
"""


# ── Public API ──────────────────────────────────────────────────────

def generate_plan(
    task_title: str,
    task_description: str = "",
    goal: dict = None,
    context_memories: list[dict] = None,
    llm: LLMClient = None,
) -> list[str]:
    """
    Générer un plan d'action pour une tâche.

    Utilise le LLM pour décomposer la tâche en 3-5 étapes
    concrètes en tenant compte du contexte.

    Args:
        task_title:       Titre de la tâche.
        task_description: Description optionnelle.
        goal:             Objectif associé (dict).
        context_memories: Mémoires pertinentes pour le contexte.
        llm:              Client LLM (en crée un si non fourni).

    Returns:
        Liste de 3-5 étapes sous forme de strings.
    """
    if llm is None:
        llm = LLMClient()

    # Build context
    context = _format_context(context_memories)
    goal_info = _format_goal(goal)

    prompt = PLANNER_PROMPT_TEMPLATE.format(
        task_title=task_title,
        task_description=task_description or "(pas de description)",
        context=context,
        goal_info=goal_info,
    )

    try:
        logger.info(f"Generating plan for: {task_title[:60]}...")

        raw_response = llm.generate(
            prompt=prompt,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=400,
        )

        steps = _parse_steps(raw_response)
        logger.info(f"Generated {len(steps)} steps")
        return steps

    except ConnectionError:
        logger.error("Cannot connect to Ollama for planning")
        return _fallback_steps(task_title)
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return _fallback_steps(task_title)


# ── Helpers ─────────────────────────────────────────────────────────

def _format_context(memories: list[dict]) -> str:
    """Format memories as context for the planner."""
    if not memories:
        return "(aucun contexte disponible)"

    parts = []
    for i, mem in enumerate(memories[:3], 1):
        q = mem.get("question", "")
        a = mem.get("answer", "")[:200]
        parts.append(f"{i}. Q: {q}\n   R: {a}")
    return "\n".join(parts)


def _format_goal(goal: dict) -> str:
    """Format a goal for the prompt."""
    if not goal:
        return "(aucun objectif spécifique)"

    return (
        f"{goal.get('title', 'Sans titre')} "
        f"(priorité: {goal.get('priority', 5)}/10, "
        f"progression: {goal.get('progress', 0)}%)\n"
        f"Description: {goal.get('description', '')}"
    )


def _parse_steps(raw_text: str) -> list[str]:
    """Parse the LLM response into individual steps."""
    if not raw_text:
        return []

    lines = raw_text.strip().split("\n")
    steps = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Remove numbering
        cleaned = re.sub(r"^(\d+[\.\)]\s*|[-•]\s*)", "", line).strip()

        if cleaned and len(cleaned) > 5:
            steps.append(cleaned)

    return steps[:5]  # Cap at 5 steps


def _fallback_steps(task_title: str) -> list[str]:
    """
    Generate basic fallback steps when LLM is unavailable.

    Provides a simple 3-step structure.
    """
    return [
        f"Rechercher des ressources sur : {task_title}",
        "Prendre des notes sur les points clés",
        "Mettre en pratique avec un exercice concret",
    ]
