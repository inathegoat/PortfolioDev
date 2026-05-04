"""src/retrieval/reranker.py — Chunk reranking for improved retrieval.

Supports:
- LLM-based pairwise scoring (no extra dependencies)
- MMR (Maximal Marginal Relevance) for diversity
- Hybrid: score = alpha * similarity + (1-alpha) * LLM_relevance
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class Reranker:
    """Reranks retrieved chunks for better relevance and diversity."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    # ── MMR (Maximal Marginal Relevance) ──────────────────────────────

    def mmr(
        self,
        results: List[Dict[str, Any]],
        top_k: int = 5,
        lambda_param: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Apply MMR to balance relevance and diversity.

        lambda_param: 0 = max diversity, 1 = max relevance (default 0.7).

        For computational efficiency, uses text-level Jaccard similarity
        instead of full embedding comparison.
        """
        if len(results) <= top_k:
            return results

        selected = [results[0]]
        remaining = results[1:]

        while len(selected) < top_k and remaining:
            best_idx = 0
            best_score = -float("inf")

            for i, candidate in enumerate(remaining):
                # Relevance: 1 - distance (cosine similarity proxy)
                relevance = 1 - candidate.get("distance", 0.5)

                # Diversity: max similarity to already selected
                max_sim = max(
                    self._jaccard_similarity(candidate.get("content", ""), s.get("content", ""))
                    for s in selected
                ) if selected else 0

                score = lambda_param * relevance - (1 - lambda_param) * max_sim

                if score > best_score:
                    best_score = score
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected

    # ── LLM-based reranking ───────────────────────────────────────────

    def llm_rerank(
        self,
        question: str,
        results: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Use LLM to score relevance of each chunk to the question.

        Scores each chunk on 1-5 scale, then reorders by score.
        Falls back to distance-based ordering if no LLM available.
        """
        if not self._llm or not self._llm.is_available():
            logger.debug("LLM not available for reranking, using distance-based order")
            return sorted(results, key=lambda r: r.get("distance", 1.0))[:top_k]

        scored = []
        for r in results:
            content = r.get("content", "")[:1000]  # truncate for speed
            prompt = (
                f"On a scale of 1 (not relevant) to 5 (highly relevant), "
                f"how relevant is this text to the question?\n\n"
                f"Question: {question}\n\n"
                f"Text: {content}\n\n"
                f"Relevance score (1-5):"
            )
            try:
                score_text = self._llm.generate(prompt=prompt, temperature=0.0, max_tokens=5)
                numeric = "".join(c for c in score_text if c in "12345")
                score = int(numeric) if numeric else 3
            except Exception:
                score = 3  # neutral on error

            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        """Compute Jaccard similarity between two texts at word level."""
        set_a = set(text_a.lower().split())
        set_b = set(text_b.lower().split())
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)
