"""src/agents_v2/retriever.py — Searches documents and returns relevant chunks.

Input: query string
Output: list of chunks with sources
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Retriever:
    """Searches the document base for relevant information."""

    def __init__(self, vector_store=None, rag_pipeline=None):
        self._vs = vector_store
        self._rag = rag_pipeline

    def search(
        self,
        query: str,
        top_k: int = 5,
        source_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks for a query.

        Args:
            query: Search query.
            top_k: Number of chunks to retrieve.
            source_filter: Optional document name to filter by.

        Returns:
            List of chunks with content, source_file, relevance.
        """
        if self._rag:
            return self._rag.retrieve_only(query)

        if self._vs:
            where = {"source": source_filter} if source_filter else None
            results = self._vs.search(query, k=top_k, where=where)
            return [
                {
                    "content": r.get("text", r.get("content", "")),
                    "source_file": r.get("source", r.get("metadata", {}).get("source_file", "")),
                    "relevance": r.get("score", 0),
                }
                for r in results
            ]

        logger.warning("No vector store or RAG pipeline available for retrieval")
        return []

    def format_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Format retrieved chunks into a context string for the LLM."""
        if not chunks:
            return "Aucune information trouvée dans les documents."

        parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source_file", "inconnu")
            content = chunk.get("content", "")[:500]
            parts.append(f"[Document {i}: {source}]\n{content}")
        return "\n\n---\n\n".join(parts)
