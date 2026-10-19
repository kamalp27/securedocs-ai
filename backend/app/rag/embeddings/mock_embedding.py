"""Mock embedding service for deterministic, fast, offline automated tests."""

import hashlib
from typing import List, Optional
import numpy as np

from app.rag.embeddings.base import (
    BaseEmbeddingService,
    InvalidVectorError,
)


class MockEmbeddingService(BaseEmbeddingService):
    """
    Deterministic pseudo-embedding generator for testing without downloading real models.
    Generates repeatable L2-normalized float32 vectors derived from text hashes.
    """

    def __init__(self, dimension: int = 384, fail_on_load: bool = False):
        if dimension <= 0:
            raise ValueError(f"dimension must be positive (got {dimension})")
        self._dimension = dimension
        self._fail_on_load = fail_on_load
        if self._fail_on_load:
            raise RuntimeError("Configured to simulate model load failure.")

    @property
    def dimension(self) -> int:
        return self._dimension

    def _word_to_vector(self, word: str) -> np.ndarray:
        seed_bytes = hashlib.md5(word.encode("utf-8")).digest()
        seed_int = int.from_bytes(seed_bytes[:4], byteorder="big")
        rng = np.random.RandomState(seed_int)
        raw = rng.randn(self._dimension).astype(np.float32)
        norm = np.linalg.norm(raw)
        return raw / (norm if norm > 0 else 1.0)

    def _hash_to_vector(self, text: str) -> np.ndarray:
        """Derive a deterministic unit vector by summing word vectors."""
        if not text or not text.strip():
            raise InvalidVectorError("Cannot generate embedding for empty text.")

        import re
        words = re.findall(r"\w+", text.lower())
        if not words:
            words = [text.strip()]

        v = sum(self._word_to_vector(w) for w in words)
        norm = np.linalg.norm(v)
        if norm == 0:
            v[0] = 1.0
            norm = 1.0
        return (v / norm).astype(np.float32)

    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dimension), dtype=np.float32)

        vectors = np.vstack([self._hash_to_vector(t) for t in texts])
        return self.normalize_vectors(vectors)

    def generate_query_embedding(self, query: str) -> np.ndarray:
        vec = self._hash_to_vector(query)
        vec_2d = np.expand_dims(vec, axis=0)
        return self.normalize_vectors(vec_2d)
