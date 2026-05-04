"""tests/test_integration.py — End-to-end integration test.

Tests the full flow: ingest document → query RAG → verify citations.
Requires Ollama to be running.
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def test_doc():
    """Create a temporary test document."""
    content = (
        "L'intelligence artificielle (IA) est un domaine de l'informatique. "
        "Le traitement automatique du langage naturel (NLP) permet aux machines "
        "de comprendre le texte humain. Les modèles de langage comme GPT et BERT "
        "ont révolutionné ce domaine depuis 2018."
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


def _ollama_available():
    """Check if Ollama is running."""
    try:
        from src.ai.llm_client import LLMClient
        return LLMClient().is_available()
    except Exception:
        return False


@pytest.mark.skipif(
    not _ollama_available(),
    reason="Ollama is not running — skip integration test",
)
class TestIntegration:
    """Full integration test: ingest → query → citations."""

    def test_ingest_and_query(self, test_doc):
        from src.ingestion.pipeline import IngestionPipeline
        from src.ai.rag_pipeline import RAGPipeline

        # Ingest
        pipeline = IngestionPipeline()
        result = pipeline.ingest_file(test_doc, force=True)
        assert result.status == "ingested", f"Ingestion failed: {result.error}"
        assert result.chunks_count >= 1

        # Query
        rag = RAGPipeline(use_reranker=True, detect_injections=True)
        response = rag.query("Qu'est-ce que le NLP?")

        # Verify answer is not empty
        assert response.answer, "Empty answer"
        assert len(response.answer) > 20, f"Answer too short: {response.answer}"

        # Verify sources exist
        assert response.sources, "No sources returned"
        assert response.num_chunks_used >= 1

        # Verify trace
        assert response.trace is not None
        assert len(response.trace.steps) >= 5

        # Verify no injection warning
        assert response.injection_warning is None

    def test_citations_present(self, test_doc):
        from src.ingestion.pipeline import IngestionPipeline
        from src.ai.rag_pipeline import RAGPipeline

        pipeline = IngestionPipeline()
        pipeline.ingest_file(test_doc, force=True)

        rag = RAGPipeline()
        response = rag.query("Parle-moi de l'intelligence artificielle")

        # Answer should contain either [Source:] or the filename
        has_citation = (
            "[Source:" in response.answer
            or test_doc.name in response.answer
        )
        assert has_citation, f"No citation found in: {response.answer[:200]}"

    def test_retrieval_only(self, test_doc):
        from src.ingestion.pipeline import IngestionPipeline
        from src.ai.rag_pipeline import RAGPipeline

        pipeline = IngestionPipeline()
        pipeline.ingest_file(test_doc, force=True)

        rag = RAGPipeline()
        results = rag.retrieve_only("intelligence artificielle")

        assert results, "No retrieval results"
        for r in results:
            assert "content" in r
            assert "distance" in r
            assert "metadata" in r
