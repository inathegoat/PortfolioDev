"""src/memory/vector_store.py — ChromaDB vector store."""
import hashlib
import logging
import uuid
from typing import Any, Dict, List, Optional

from config.settings import CHROMA_DIR, EMBEDDING_MODEL, MAX_CONTEXT_CHUNKS, CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)


class VectorStore:
    """Interface ChromaDB pour le stockage et la recherche sémantique."""

    COLLECTION = "second_brain"

    def __init__(self):
        import chromadb
        from chromadb.config import Settings
        self._client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=self.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = None  # lazy init

    # ── Embeddings ───────────────────────────────────────────────────

    def _embed(self, texts: List[str]) -> List[List[float]]:
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedder.encode(texts, show_progress_bar=False).tolist()

    # ── Ingestion ────────────────────────────────────────────────────

    def add_document(
        self,
        text: str,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> int:
        """Découpe un texte en chunks et les indexe dans ChromaDB."""
        chunks = self._chunk(text, chunk_size, chunk_overlap)
        if not chunks:
            return 0

        embeddings = self._embed(chunks)
        ids, docs, embeds, metas = [], [], [], []

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            doc_id = hashlib.md5(f"{source}_{i}_{chunk[:50]}".encode()).hexdigest()
            ids.append(doc_id)
            docs.append(chunk)
            embeds.append(emb)
            metas.append({
                "source": source,
                "source_file": source,
                "chunk_index": i,
                "total_chunks": len(chunks),
                **(metadata or {}),
            })

        self._col.upsert(ids=ids, documents=docs, embeddings=embeds, metadatas=metas)
        logger.info(f"Indexed {len(chunks)} chunks from: {source}")
        return len(chunks)

    # ── Recherche ─────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        k: int = MAX_CONTEXT_CHUNKS,
        where: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Recherche sémantique — retourne les k chunks les plus proches."""
        if self._col.count() == 0:
            return []
        query_emb = self._embed([query])[0]
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_emb],
            "n_results": min(k, self._col.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._col.query(**kwargs)
        out = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            out.append({
                "text": doc,
                "content": doc,              # alias for RAG pipeline compatibility
                "source": meta.get("source", ""),
                "score": round(1 - dist, 4), # cosine similarity
                "distance": dist,            # alias for RAG pipeline compatibility
                "metadata": meta,
            })
        return out

    def query(
        self,
        query_embedding: List[float],
        top_k: int = MAX_CONTEXT_CHUNKS,
        where: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Recherche sémantique par vecteur d'embedding (appelée par RAG pipeline)."""
        if self._col.count() == 0:
            return []
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, self._col.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        results = self._col.query(**kwargs)
        out = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            out.append({
                "text": doc,
                "content": doc,
                "source": meta.get("source", ""),
                "score": round(1 - dist, 4),
                "distance": dist,
                "metadata": meta,
            })
        return out

    # ── Utilitaires ───────────────────────────────────────────────────

    def list_sources(self) -> List[str]:
        """Liste toutes les sources uniques indexées."""
        if self._col.count() == 0:
            return []
        results = self._col.get(include=["metadatas"])
        sources = {m.get("source", "") for m in results["metadatas"]}
        return sorted(s for s in sources if s)

    def delete_source(self, source: str) -> int:
        """Supprime tous les chunks d'une source."""
        results = self._col.get(where={"source": source}, include=["metadatas"])
        ids = results.get("ids", [])
        if ids:
            self._col.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        return self._col.count()

    def reset(self):
        """Supprime toute la collection."""
        self._client.delete_collection(self.COLLECTION)
        self._col = self._client.get_or_create_collection(
            name=self.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        chunks,
        doc_id: str = "",
        embeddings: Optional[List[List[float]]] = None,
        source_file: str = "",
        file_type: str = "",
        metadata: Optional[Dict] = None,
    ) -> int:
        """Indexe une liste d'objets Chunk (appelée par main.py cmd_ingest).
        
        Si `embeddings` est fourni (pré-calculé par Embedder), on les utilise directement.
        Sinon, on les calcule en interne.
        """
        texts = [c.content if hasattr(c, "content") else str(c) for c in chunks]
        if not texts:
            return 0
        if embeddings is None:
            embeddings = self._embed(texts)
        ids, docs, embeds, metas = [], [], [], []
        for i, (chunk_text, emb) in enumerate(zip(texts, embeddings)):
            chunk_id = hashlib.md5(f"{doc_id}_{i}_{chunk_text[:50]}".encode()).hexdigest()
            ids.append(chunk_id)
            docs.append(chunk_text)
            embeds.append(emb)
            chunk_meta = {
                "source": source_file,
                "source_file": source_file,
                "file_type": file_type,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "doc_id": doc_id,
                **(metadata or {}),
            }
            if hasattr(chunks[i], "metadata") and isinstance(chunks[i].metadata, dict):
                chunk_meta.update(chunks[i].metadata)
            metas.append(chunk_meta)
        self._col.upsert(ids=ids, documents=docs, embeddings=embeds, metadatas=metas)
        logger.info(f"add_chunks: indexed {len(chunks)} chunks from: {source_file}")
        return len(chunks)

    def get_stats(self) -> Dict[str, Any]:
        """Statistiques du vector store (appelée par main.py cmd_stats)."""
        n = self._col.count()
        return {
            "total_chunks": n,
            "total_sources": len(self.list_sources()),
            "collection": self.COLLECTION,
        }

    def delete_document(self, doc_id: str) -> int:
        """Supprime les chunks d'un document par ID (appelée par main.py cmd_delete)."""
        return self.delete_source(doc_id)

    @staticmethod
    def _chunk(text: str, size: int = 512, overlap: int = 64) -> List[str]:
        """Fenêtre glissante sur les mots."""
        words = text.split()
        if not words:
            return []
        chunks, i = [], 0
        while i < len(words):
            chunk = " ".join(words[i: i + size])
            chunks.append(chunk)
            i += size - overlap
        return [c for c in chunks if len(c.strip()) > 20]
