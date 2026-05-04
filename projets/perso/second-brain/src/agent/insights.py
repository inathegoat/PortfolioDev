"""
Second Brain — Insight Generator (Phase 3)
=============================================
Uses the local LLM to generate actionable insights from ranked memories.

Takes the top-scored memories from the attention system, combines them
with the user's goals, and asks the LLM to identify patterns and suggest
concrete next actions.

Insights are short, actionable strings — not essays.
"""

import logging
import re

from src.ai.llm_client import LLMClient
from src.goals import load_goals

logger = logging.getLogger(__name__)

# ── Insight Prompt ──────────────────────────────────────────────────

INSIGHT_SYSTEM_PROMPT = """Tu es un assistant IA proactif qui analyse les schémas de connaissances de l'utilisateur.
Ton rôle est d'identifier des connexions et de suggérer des actions concrètes.

Règles :
1. Sois spécifique et actionnable — pas de conseils vagues.
2. Référence les sujets réels des mémoires de l'utilisateur.
3. Relie différentes connaissances quand c'est possible.
4. Suggère des actions d'étude ou d'exploration concrètes.
5. Limite chaque insight à 1-2 phrases maximum.
6. Retourne UNIQUEMENT une liste numérotée d'insights (3-5 éléments).
7. N'inclus AUCUN préambule, explication ou remarque de clôture.
8. Réponds TOUJOURS en français.
"""

INSIGHT_PROMPT_TEMPLATE = """En te basant sur l'activité de connaissance récente et les objectifs de l'utilisateur, génère des insights actionnables.

=== OBJECTIFS DE L'UTILISATEUR ===
{goals_text}

=== MÉMOIRES IMPORTANTES RÉCENTES ===
{memories_text}

=== TÂCHE ===
Analyse les mémoires ci-dessus dans le contexte des objectifs de l'utilisateur.
Identifie :
- Les schémas ou thèmes récurrents
- Les lacunes de connaissances à combler
- Les connexions entre différents sujets
- Les prochaines étapes concrètes que l'utilisateur devrait entreprendre

Retourne une liste numérotée de 3 à 5 insights courts et actionnables, en français.
"""


# ── Public API ──────────────────────────────────────────────────────

def generate_insights(
    ranked_memories: list[dict],
    goals: list[dict] = None,
    llm: LLMClient = None,
    top_n: int = 5,
) -> list[str]:
    """
    Generate actionable insights from ranked memories.

    Pipeline:
    1. Select top N most important memories
    2. Build structured context with goals
    3. Call local LLM for insight generation
    4. Parse and filter the response

    Args:
        ranked_memories: Memories sorted by attention score (descending).
        goals:           User goals (loaded from file if not provided).
        llm:             LLM client (creates one if not provided).
        top_n:           Number of top memories to analyze.

    Returns:
        List of actionable insight strings.
    """
    if not ranked_memories:
        logger.info("No memories to analyze")
        return []

    if goals is None:
        goals = load_goals()

    if llm is None:
        llm = LLMClient()

    # ── Step 1: Select top memories ─────────────────────────────────
    top_memories = ranked_memories[:top_n]

    # ── Step 2: Build the prompt ────────────────────────────────────
    goals_text = _format_goals(goals)
    memories_text = _format_memories(top_memories)

    prompt = INSIGHT_PROMPT_TEMPLATE.format(
        goals_text=goals_text,
        memories_text=memories_text,
    )

    # ── Step 3: Call the LLM ────────────────────────────────────────
    try:
        logger.info(f"Generating insights from {len(top_memories)} memories...")

        raw_response = llm.generate(
            prompt=prompt,
            system_prompt=INSIGHT_SYSTEM_PROMPT,
            temperature=0.4,   # Slightly creative but focused
            max_tokens=500,    # Keep insights concise
        )

        # ── Step 4: Parse and filter ────────────────────────────────
        insights = _parse_insights(raw_response)
        insights = _filter_trivial(insights)

        logger.info(f"Generated {len(insights)} insights")
        return insights

    except ConnectionError:
        logger.error("Cannot connect to Ollama for insight generation")
        return []
    except Exception as e:
        logger.error(f"Insight generation failed: {e}")
        return []


# ── Formatting Helpers ──────────────────────────────────────────────

def _format_goals(goals: list[dict]) -> str:
    """Format goals into a readable string for the prompt."""
    if not goals:
        return "No specific goals defined."

    parts = []
    for goal in goals:
        parts.append(
            f"- [{goal.get('priority', 5)}/10] {goal.get('title', 'Untitled')} "
            f"(progress: {goal.get('progress', 0)}%): "
            f"{goal.get('description', '')}"
        )
    return "\n".join(parts)


def _format_memories(memories: list[dict]) -> str:
    """Format ranked memories into a readable string for the prompt."""
    parts = []
    for i, mem in enumerate(memories, 1):
        score = mem.get("attention_score", 0)
        matched = mem.get("matched_goals", [])
        goals_str = f" [Goals: {', '.join(matched)}]" if matched else ""

        parts.append(
            f"Memory {i} (importance: {score:.2f}){goals_str}:\n"
            f"  Q: {mem.get('question', '')}\n"
            f"  A: {mem.get('answer', '')[:300]}"
        )
    return "\n\n".join(parts)


def _parse_insights(raw_text: str) -> list[str]:
    """
    Parse the LLM's response into individual insight strings.

    Handles numbered lists (1. ..., 2. ...) and bullet lists (- ...).
    """
    if not raw_text:
        return []

    lines = raw_text.strip().split("\n")
    insights = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Remove numbering: "1. ", "2) ", "- ", "• "
        cleaned = re.sub(r"^(\d+[\.\)]\s*|[-•]\s*)", "", line).strip()

        if cleaned and len(cleaned) > 10:
            insights.append(cleaned)

    return insights


def _filter_trivial(insights: list[str]) -> list[str]:
    """
    Filter out trivial or generic insights.

    Removes insights that are too short, too generic,
    or contain common filler phrases.
    """
    trivial_phrases = [
        "continue d'apprendre",
        "continue à étudier",
        "bon travail",
        "bien joué",
        "continue comme ça",
        "reste concentré",
        "n'oublie pas de réviser",
        "keep learning",
        "continue studying",
        "good job",
    ]

    filtered = []
    for insight in insights:
        # Skip if too short
        if len(insight) < 20:
            continue

        # Skip if trivially generic
        insight_lower = insight.lower()
        if any(phrase in insight_lower for phrase in trivial_phrases):
            continue

        filtered.append(insight)

    return filtered
