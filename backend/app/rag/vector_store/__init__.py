"""Vector store exports and singleton lifecycle factory."""

from typing import Optional
from app.rag.vector_store.faiss_store import (
    DimensionMismatchError,
    FAISSVectorStore,
    IndexCorruptedError,
    IndexNotFoundError,
    PathTraversalError,
    VectorStoreError,
)

_global_vector_store: Optional[FAISSVectorStore] = None


def get_vector_store() -> FAISSVectorStore:
    """Retrieve or initialize the global vector store instance."""
    global _global_vector_store
    if _global_vector_store is None:
        _global_vector_store = FAISSVectorStore()
    return _global_vector_store


def set_vector_store(store: Optional[FAISSVectorStore]) -> None:
    """Override the global vector store instance (useful for test isolation)."""
    global _global_vector_store
    _global_vector_store = store


__all__ = [
    "FAISSVectorStore",
    "VectorStoreError",
    "IndexNotFoundError",
    "IndexCorruptedError",
    "DimensionMismatchError",
    "PathTraversalError",
    "get_vector_store",
    "set_vector_store",
]