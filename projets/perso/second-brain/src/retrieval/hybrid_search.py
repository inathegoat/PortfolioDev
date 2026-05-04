"""src/retrieval/hybrid_search.py — Hybrid retrieval: vector + lexical.

Combines:
- Vector similarity (ChromaDB cosine)
- Lexical matching (BM25-like TF-IDF scoring)

Score = alpha * vector_score + (1-alpha) * lexical_score

Ensures both semantic AND keyword matches contribute to ranking.
"""
import logging
import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LexicalScorer:
    """TF-IDF style lexical scorer for document chunks."""

    def __init__(self):
        self._doc_freq: Dict[str, int] = defaultdict(int)
        self._total_docs: int = 0

    def index(self, chunks: List[Dict[str, Any]]):
        """Build term-frequency index from a list of chunks."""
        for chunk in chunks:
            content = chunk.get("content", "")
            terms = self._tokenize(content)
            for term in set(terms):
                self._doc_freq[term] += 1
            self._total_docs += 1
        logger.info(f"LexicalScorer indexed {self._total_docs} docs, {len(self._doc_freq)} terms")

    def score(self, query: str, chunk_content: str) -> float:
        """Compute BM25-like lexical relevance score.

        Returns score in [0, 1], normalized by query length.
        """
        if not self._doc_freq or self._total_docs == 0:
            return 0.0

        query_terms = self._tokenize(query)
        if not query_terms:
            return 0.0

        chunk_terms = self._tokenize(chunk_content)
        if not chunk_terms:
            return 0.0

        # TF computation for chunk
        tf = defaultdict(int)
        for t in chunk_terms:
            tf[t] += 1

        # BM25-like scoring
        k1 = 1.5  # term saturation
        b = 0.75   # length normalization
        avg_dl = max(1, sum(len(self._tokenize(" ")) for _ in range(1)))

        score = 0.0
        doc_len = len(chunk_terms)

        for term in set(query_terms):
            if term not in tf:
                continue
            # IDF
            df = self._doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (self._total_docs - df + 0.5) / (df + 0.5))
            # TF (BM25)
            tf_score = (tf[term] * (k1 + 1)) / (tf[term] + k1 * (1 - b + b * doc_len / max(1, avg_dl)))
            score += idf * tf_score

        # Normalize by query length
        return min(score / max(1, len(query_terms)), 1.0)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize text into lowercase word tokens (min 2 chars)."""
        return [
            t.lower() for t in re.findall(r'\w{2,}', text)
            if t.lower() not in _STOP_WORDS and len(t) >= 2
        ]


# French + English stop words
_STOP_WORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "est",
    "à", "au", "aux", "en", "dans", "sur", "pour", "par", "avec",
    "ce", "cette", "ces", "que", "qui", "dont", "où", "il", "elle",
    "ils", "elles", "nous", "vous", "leur", "leurs", "son", "sa", "ses",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "of", "in", "to", "for", "with", "on", "at", "by", "from",
    "and", "or", "but", "not", "this", "that", "it", "as", "so",
    "plus", "tout", "tous", "toute", "toutes", "aussi", "très",
    "alors", "donc", "être", "avoir", "faire", "peut", "peuvent",
}


class HybridSearcher:
    """Combines vector and lexical search for improved retrieval.

    Usage:
        searcher = HybridSearcher(vector_store, alpha=0.7)
        searcher.index()  # builds lexical index from existing chunks
        results = searcher.search("algèbre linéaire", top_k=5)
    """

    def __init__(
        self,
        vector_store=None,
        alpha: float = 0.7,  # weight of vector vs lexical (higher = more vector)
    ):
        self.vector_store = vector_store
        self.alpha = alpha
        self.lexical = LexicalScorer()
        self._indexed = False

    def index(self):
        """Build lexical index from all chunks in the vector store."""
        if not self.vector_store or self.vector_store.count() == 0:
            logger.warning("No chunks to index for hybrid search")
            return

        # Get all chunks (limit to avoid memory issues)
        all_results = self.vector_store.search(
            query="",  # dummy query, we just need the full collection
            k=min(self.vector_store.count(), 5000),
        )
        # ChromaDB search requires a non-empty query, so use a workaround:
        # We'll index lazily during search instead
        self._indexed = False
        logger.info("HybridSearcher will index lazily on first search")

    def search(
        self,
        query: str,
        top_k: int = 5,
        alpha: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Hybrid search: vector + lexical.

        Args:
            query: Search query.
            top_k: Number of results.
            alpha: Vector weight (default self.alpha). 1.0 = pure vector.

        Returns:
            List of results with hybrid_score added.
        """
        if alpha is None:
            alpha = self.alpha

        if not self.vector_store:
            return []

        # Step 1: Vector search (fetch more for reranking)
        fetch_k = min(top_k * 3, 20)
        vector_results = self.vector_store.search(query, k=fetch_k)

        if not vector_results:
            return []

        # Step 2: Build lexical index lazily from results
        if not self._indexed:
            self.lexical.index(vector_results)
            self._indexed = True

        # Step 3: Compute hybrid scores
        max_vector_score = max(
            r.get("score", 0) for r in vector_results
        ) or 1.0

        for r in vector_results:
            vector_score = r.get("score", 0) / max_vector_score if max_vector_score else 0
            content = r.get("content", r.get("text", ""))
            lexical_score = self.lexical.score(query, content)
            hybrid = alpha * vector_score + (1 - alpha) * lexical_score
            r["vector_score"] = round(vector_score, 4)
            r["lexical_score"] = round(lexical_score, 4)
            r["hybrid_score"] = round(hybrid, 4)

        # Step 4: Rerank by hybrid score
        scored = sorted(vector_results, key=lambda r: r.get("hybrid_score", 0), reverse=True)

        return scored[:top_k]
