"""Embedding service exports and application singleton factory."""

from typing import Optional
from app.rag.embeddings.base import (
    BaseEmbeddingService,
    EmbeddingDimensionError,
    EmbeddingError,
    InvalidVectorError,
    ModelLoadError,
)
from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingService
from app.rag.embeddings.mock_embedding import MockEmbeddingService

_global_embedding_service: Optional[BaseEmbeddingService] = None


def get_embedding_service() -> BaseEmbeddingService:
    """Retrieve or initialize the global embedding service instance."""
    global _global_embedding_service
    if _global_embedding_service is None:
        _global_embedding_service = SentenceTransformerEmbeddingService()
    return _global_embedding_service


def set_embedding_service(service: Optional[BaseEmbeddingService]) -> None:
    """Override the global embedding service instance (useful for test dependency injection)."""
    global _global_embedding_service
    _global_embedding_service = service


__all__ = [
    "BaseEmbeddingService",
    "EmbeddingError",
    "ModelLoadError",
    "EmbeddingDimensionError",
    "InvalidVectorError",
    "SentenceTransformerEmbeddingService",
    "MockEmbeddingService",
    "get_embedding_service",
    "set_embedding_service",
]