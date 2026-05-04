"""
Second Brain — Embedding Generator
====================================
Generates vector embeddings from text using sentence-transformers.

Uses a singleton pattern to load the model once and reuse it.
The model runs entirely locally — no API calls, no cloud.

Default model: all-MiniLM-L6-v2
- Size: ~80MB
- Dimensions: 384
- Speed: Very fast on CPU
- Quality: Good for English text retrieval
"""

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from config.settings import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class Embedder:
    """
    Generates text embeddings using a local sentence-transformers model.
    
    Usage:
        embedder = Embedder()
        vectors = embedder.embed_texts(["Hello world", "How are you?"])
        query_vec = embedder.embed_query("What is this about?")
    """
    
    # Singleton instance — model is loaded once
    _instance: Optional["Embedder"] = None
    _model: Optional[SentenceTransformer] = None
    
    def __new__(cls, model_name: str = EMBEDDING_MODEL):
        """Singleton: reuse the same instance and loaded model."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        """
        Initialize the embedder (loads model on first call).
        
        Args:
            model_name: Name of the sentence-transformers model.
                       Default: all-MiniLM-L6-v2
        """
        if Embedder._model is None:
            logger.info(f"Loading embedding model: {model_name}")
            Embedder._model = SentenceTransformer(model_name)
            self._model_name = model_name
            logger.info(
                f"Model loaded. Dimensions: "
                f"{Embedder._model.get_embedding_dimension()}"
            )
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.
        
        Uses batch processing for efficiency — much faster than
        embedding one text at a time.
        
        Args:
            texts: List of text strings to embed.
        
        Returns:
            List of embedding vectors (each is a list of floats).
        """
        if not texts:
            return []
        
        logger.info(f"Embedding {len(texts)} texts...")
        
        # Batch encode for efficiency
        embeddings = Embedder._model.encode(
            texts,
            show_progress_bar=len(texts) > 10,  # Show bar for large batches
            normalize_embeddings=True,           # L2 normalize for cosine similarity
        )
        
        # Convert numpy arrays to Python lists (for ChromaDB compatibility)
        result = embeddings.tolist()
        
        logger.info(f"Generated {len(result)} embeddings")
        return result
    
    def embed_query(self, query: str) -> list[float]:
        """
        Generate embedding for a single query string.
        
        Args:
            query: The query text to embed.
        
        Returns:
            Embedding vector as a list of floats.
        """
        if not query.strip():
            raise ValueError("Cannot embed empty query")
        
        embedding = Embedder._model.encode(
            query,
            normalize_embeddings=True,
        )
        
        return embedding.tolist()
    
    @property
    def dimensions(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        return Embedder._model.get_embedding_dimension()
    
    @property
    def model_name(self) -> str:
        """Return the name of the loaded model."""
        return getattr(self, "_model_name", EMBEDDING_MODEL)
