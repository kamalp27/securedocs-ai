"""Base embedding service interfaces and error hierarchies."""

from abc import ABC, abstractmethod
from typing import List
import numpy as np


class EmbeddingError(Exception):
    """Base exception for text embedding generation failures."""
    pass


class ModelLoadError(EmbeddingError):
    """Raised when an embedding model cannot be loaded from disk or network."""
    pass


class EmbeddingDimensionError(EmbeddingError):
    """Raised when generated vector dimensions do not match the expected model dimension."""
    pass


class InvalidVectorError(EmbeddingError):
    """Raised when generated embeddings contain NaN, infinite, or zero-norm vectors."""
    pass


class BaseEmbeddingService(ABC):
    """Abstract base class for deterministic, unit-normalized text embedding services."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality of the embedding model."""
        pass

    @abstractmethod
    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate unit-normalized embeddings for a list of input text chunks.
        
        Returns:
            np.ndarray of shape (len(texts), dimension) and dtype np.float32.
        
        Raises:
            EmbeddingError, InvalidVectorError
        """
        pass

    @abstractmethod
    def generate_query_embedding(self, query: str) -> np.ndarray:
        """
        Generate a unit-normalized embedding vector for a single query string.
        
        Returns:
            np.ndarray of shape (1, dimension) and dtype np.float32.
        
        Raises:
            EmbeddingError, InvalidVectorError
        """
        pass

    @staticmethod
    def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
        """
        L2-normalize a 2D matrix of vectors to unit length for cosine similarity.
        Validates that all vector components are finite (no NaN, Inf).
        """
        if not np.isfinite(vectors).all():
            raise InvalidVectorError("Generated embeddings contain non-finite values (NaN or Inf).")

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        # Prevent division by zero for empty or degenerate vectors
        zero_norm_mask = (norms == 0).flatten()
        if np.any(zero_norm_mask):
            raise InvalidVectorError("Generated embedding contains zero-magnitude vector.")

        return (vectors / norms).astype(np.float32)
