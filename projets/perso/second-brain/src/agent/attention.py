"""
Second Brain — Attention System (Phase 3)
==========================================
Scores and ranks memories by importance.

Every memory gets a combined score based on 4 factors:
  - Recency   (30%): recent memories score higher (exponential decay)
  - Frequency (20%): topics that appear repeatedly score higher
  - Goal alignment (35%): memories matching user goals score highest
  - Depth     (15%): longer / more complex content scores higher

This allows the brain loop to focus on what matters most.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional

from src.goals import match_goals, load_goals

logger = logging.getLogger(__name__)

# ── Scoring Weights ─────────────────────────────────────────────────
# These must sum to 1.0

WEIGHT_RECENCY = 0.30
WEIGHT_FREQUENCY = 0.20
WEIGHT_GOAL_ALIGNMENT = 0.35
WEIGHT_DEPTH = 0.15

# ── Decay Constant ──────────────────────────────────────────────────
# Half-life of ~50 hours: memories from 3 days ago score ~0.36
RECENCY_DECAY_HOURS = 72.0


# ── Public API ──────────────────────────────────────────────────────

def compute_score(
    memory: dict,
    all_memories: list[dict],
    goals: list[dict] = None,
) -> float:
    """
    Compute an importance score for a single memory.

    Args:
        memory:        A single interaction dict (question, answer, timestamp).
        all_memories:  All memories (used for frequency analysis).
        goals:         User goals (loaded from file if not provided).

    Returns:
        Score between 0.0 and 1.0.
    """
    if goals is None:
        goals = load_goals()

    text = _memory_text(memory)

    recency = _score_recency(memory)
    frequency = _score_frequency(text, all_memories)
    alignment = _score_goal_alignment(text, goals)
    depth = _score_depth(text)

    score = (
        WEIGHT_RECENCY * recency
        + WEIGHT_FREQUENCY * frequency
        + WEIGHT_GOAL_ALIGNMENT * alignment
        + WEIGHT_DEPTH * depth
    )

    # Clamp to [0, 1]
    return max(0.0, min(1.0, score))


def rank_memories(
    memories: list[dict],
    goals: list[dict] = None,
) -> list[dict]:
    """
    Rank all memories by importance score.

    Each memory dict gets two new keys:
      - attention_score: the computed score
      - matched_goals:   list of matched goal titles

    Args:
        memories: All interaction dicts.
        goals:    User goals (loaded from file if not provided).

    Returns:
        Memories sorted by attention_score descending.
    """
    if not memories:
        return []

    if goals is None:
        goals = load_goals()

    scored = []
    for memory in memories:
        score = compute_score(memory, memories, goals)

        # Find matched goals for context
        text = _memory_text(memory)
        goal_matches = match_goals(text, goals)
        matched_titles = [m["goal"]["title"] for m in goal_matches]

        enriched = {
            **memory,
            "attention_score": round(score, 4),
            "matched_goals": matched_titles,
        }
        scored.append(enriched)

    # Sort by score descending
    scored.sort(key=lambda m: m["attention_score"], reverse=True)

    logger.info(
        f"Ranked {len(scored)} memories | "
        f"top={scored[0]['attention_score']:.3f} "
        f"bottom={scored[-1]['attention_score']:.3f}"
    )

    return scored


# ── Scoring Functions ───────────────────────────────────────────────

def _score_recency(memory: dict) -> float:
    """
    Score based on how recent the memory is.

    Uses exponential decay: score = exp(-hours_ago / DECAY_HOURS)
    - Just now  → ~1.0
    - 3 days ago → ~0.36
    - 1 week ago → ~0.10

    Returns:
        Score between 0.0 and 1.0.
    """
    timestamp_str = memory.get("timestamp", "")
    if not timestamp_str:
        return 0.0

    try:
        ts = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        hours_ago = (now - ts).total_seconds() / 3600.0
        return math.exp(-hours_ago / RECENCY_DECAY_HOURS)
    except (ValueError, TypeError):
        return 0.0


def _score_frequency(text: str, all_memories: list[dict]) -> float:
    """
    Score based on how often this topic appears in other memories.

    Extracts significant words from the text and counts how many
    other memories contain the same words.

    Returns:
        Score between 0.0 and 1.0 (normalized).
    """
    if not text or not all_memories:
        return 0.0

    # Extract significant words (>4 chars, skip common words)
    words = _extract_keywords(text)
    if not words:
        return 0.0

    # Count how many other memories share these words
    match_count = 0
    for other in all_memories:
        other_text = _memory_text(other).lower()
        if any(w in other_text for w in words):
            match_count += 1

    # Subtract 1 (self-match) and normalize
    match_count = max(0, match_count - 1)

    # Normalize: 5+ matches = maximum score
    return min(match_count / 5.0, 1.0)


def _score_goal_alignment(text: str, goals: list[dict]) -> float:
    """
    Score based on how well the memory aligns with user goals.

    Uses keyword matching from the goals module.

    Returns:
        Score between 0.0 and 1.0.
    """
    if not text or not goals:
        return 0.0

    matches = match_goals(text, goals)
    if not matches:
        return 0.0

    # Total matched keywords across all goals, weighted by priority
    total_score = sum(m["match_score"] for m in matches)

    # Normalize: score of 20+ = maximum (e.g., 2 goals × 3 keywords × priority 5)
    return min(total_score / 20.0, 1.0)


def _score_depth(text: str) -> float:
    """
    Score based on content length/complexity.

    Longer, more detailed answers indicate deeper engagement.

    Returns:
        Score between 0.0 and 1.0.
    """
    if not text:
        return 0.0

    # Normalize: 500+ chars = maximum depth score
    return min(len(text) / 500.0, 1.0)


# ── Helpers ─────────────────────────────────────────────────────────

def _memory_text(memory: dict) -> str:
    """Combine question and answer into a single text for analysis."""
    question = memory.get("question", "")
    answer = memory.get("answer", "")
    return f"{question} {answer}"


# Common English stop words to skip during frequency analysis
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can", "shall",
    "this", "that", "these", "those", "it", "its", "they", "them",
    "their", "we", "our", "you", "your", "he", "she", "him", "her",
    "not", "no", "nor", "so", "if", "then", "than", "too", "very",
    "just", "about", "above", "after", "before", "between", "into",
    "through", "during", "each", "some", "such", "only", "also",
    "more", "most", "other", "which", "what", "when", "where", "how",
    "all", "both", "same", "here", "there", "who", "whom", "because",
}


def _extract_keywords(text: str) -> set[str]:
    """
    Extract significant keywords from text.

    Filters out short words and common stop words.

    Returns:
        Set of lowercase keyword strings.
    """
    words = set()
    for word in text.lower().split():
        # Clean punctuation
        cleaned = word.strip(".,;:!?()[]{}\"'")
        if len(cleaned) > 4 and cleaned not in _STOP_WORDS:
            words.add(cleaned)
    return words
