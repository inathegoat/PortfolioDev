"""src/ingestion/pipeline.py — Unified document ingestion pipeline.

Single entry point for document ingestion used by both CLI and API.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.core.errors import IngestionError
from src.processing.parsers import parse_document
from src.processing.chunker import chunk_text
from src.processing.embedder import Embedder
from src.memory.vector_store import VectorStore
from src.data_layer.document_manager import DocumentManager
from config.settings import CHUNK_SIZE, CHUNK_OVERLAP, ALLOWED_EXTENSIONS

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of ingesting a single document."""
    doc_id: str
    filename: str
    file_type: str
    chunks_count: int
    status: str  # "ingested", "skipped", "error"
    error: Optional[str] = None


class IngestionPipeline:
    """Unified document ingestion pipeline.

    Usage:
        pipeline = IngestionPipeline()
        result = pipeline.ingest_file(Path("data/raw/doc.pdf"))
    """

    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        vector_store: Optional[VectorStore] = None,
        doc_manager: Optional[DocumentManager] = None,
    ):
        self.embedder = embedder or Embedder()
        self.vector_store = vector_store or VectorStore()
        self.doc_manager = doc_manager or DocumentManager()

    def ingest_file(
        self,
        file_path: Path,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest a single file: parse → chunk → embed → store.

        Args:
            file_path: Path to the document.
            force: If True, re-ingest even if already ingested.

        Returns:
            IngestionResult with status and metadata.
        """
        if not file_path.exists():
            raise IngestionError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise IngestionError(f"Unsupported format: {suffix}")

        filename = file_path.name

        # Deduplication: skip already ingested files
        if not force and self.doc_manager.is_already_ingested(file_path):
            logger.info(f"Skipping already ingested: {filename}")
            return IngestionResult(
                doc_id="", filename=filename, file_type=suffix,
                chunks_count=0, status="skipped",
            )

        # Step 1: Register document (also deduplicates by hash)
        doc_id = self.doc_manager.register_document(file_path, status="pending")

        try:
            # Step 2: Parse
            parsed = parse_document(file_path)
            logger.info(f"Parsed {filename}: {parsed.metadata.get('word_count', '?')} words")

            # Step 3: Chunk
            chunks = chunk_text(
                text=parsed.content,
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
                doc_id=doc_id,
                source_file=filename,
            )
            logger.info(f"Chunked {filename}: {len(chunks)} chunks")

            if not chunks:
                self.doc_manager.update_status(doc_id, "error")
                return IngestionResult(
                    doc_id=doc_id, filename=filename, file_type=suffix,
                    chunks_count=0, status="error",
                    error="No content extracted",
                )

            # Step 4: Embed
            texts = [c.content for c in chunks]
            embeddings = self.embedder.embed_texts(texts)
            logger.info(f"Embedded {filename}: {len(embeddings)} vectors")

            # Step 5: Store in ChromaDB
            self.vector_store.add_chunks(
                chunks=chunks,
                doc_id=doc_id,
                embeddings=embeddings,
                source_file=filename,
                file_type=suffix,
            )

            # Step 6: Update metadata
            self.doc_manager.update_status(doc_id, "ingested", chunk_count=len(chunks))

            return IngestionResult(
                doc_id=doc_id,
                filename=filename,
                file_type=suffix,
                chunks_count=len(chunks),
                status="ingested",
            )

        except Exception as e:
            logger.error(f"Ingestion failed for {filename}: {e}", exc_info=True)
            self.doc_manager.update_status(doc_id, "error")
            return IngestionResult(
                doc_id=doc_id,
                filename=filename,
                file_type=suffix,
                chunks_count=0,
                status="error",
                error=str(e),
            )

    def ingest_directory(
        self,
        directory: Optional[Path] = None,
    ) -> list[IngestionResult]:
        """Ingest all supported files in a directory.

        Args:
            directory: Directory to scan. Defaults to RAW_DIR from config.

        Returns:
            List of IngestionResult for each file processed.
        """
        from config.settings import RAW_DIR
        directory = directory or RAW_DIR

        if not directory.exists():
            logger.warning(f"Directory not found: {directory}")
            return []

        files = sorted(
            f for f in directory.iterdir()
            if f.is_file()
            and f.suffix.lower() in ALLOWED_EXTENSIONS
            and not f.name.startswith(".")
        )

        results = []
        for file_path in files:
            try:
                result = self.ingest_file(file_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process {file_path.name}: {e}")
                results.append(IngestionResult(
                    doc_id="", filename=file_path.name,
                    file_type=file_path.suffix, chunks_count=0,
                    status="error", error=str(e),
                ))
        return results
