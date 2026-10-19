"""Sentence Transformers embedding service with lazy model loading and L2-normalization."""

import logging
import threading
from typing import List, Optional
import numpy as np

from app.core.config import settings
from app.rag.embeddings.base import (
    BaseEmbeddingService,
    EmbeddingError,
    InvalidVectorError,
    ModelLoadError,
)

logger = logging.getLogger("securedocs.embeddings")


class SentenceTransformerEmbeddingService(BaseEmbeddingService):
    """
    Production embedding service utilizing local Sentence Transformers models.
    Supports lazy singleton loading, L2-normalization, and dimension validation.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        cache_folder: Optional[str] = None,
        batch_size: int = 32,
    ):
        self._model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self._device = device or settings.EMBEDDING_DEVICE
        self._cache_folder = cache_folder or settings.EMBEDDING_CACHE_DIR
        self._batch_size = batch_size

        self._model = None
        self._dimension: Optional[int] = None
        self._lock = threading.Lock()

    def _load_model(self):
        """Lazy load SentenceTransformer model in a thread-safe manner."""
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            try:
                from sentence_transformers import SentenceTransformer

                logger.info(
                    "Loading local embedding model '%s' on device '%s'...",
                    self._model_name,
                    self._device,
                )
                self._model = SentenceTransformer(
                    model_name_or_path=self._model_name,
                    device=self._device,
                    cache_folder=self._cache_folder,
                )
                self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(
                    "Embedding model '%s' loaded successfully. Dimension: %d",
                    self._model_name,
                    self._dimension,
                )

            except Exception as e:
                logger.error("Failed to load embedding model '%s': %s", self._model_name, e)
                raise ModelLoadError(
                    f"Could not load embedding model '{self._model_name}'. "
                    f"Ensure model weights are cached or internet connection is active on first run: {e}"
                ) from e

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._load_model()
        return self._dimension  # type: ignore

    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Batch generate unit-normalized embeddings for a list of document chunks.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        self._load_model()

        # Reject completely empty or null chunk strings
        sanitized_texts = []
        for i, t in enumerate(texts):
            clean = t.strip() if t else ""
            if not clean:
                raise InvalidVectorError(f"Cannot generate embedding for empty text chunk at index {i}.")
            sanitized_texts.append(clean)

        try:
            raw_embeddings = self._model.encode(  # type: ignore
                sanitized_texts,
                batch_size=self._batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=False,  # Normalize explicitly via base class for validation
            )
            raw_embeddings = np.asarray(raw_embeddings, dtype=np.float32)
            return self.normalize_vectors(raw_embeddings)

        except InvalidVectorError:
            raise
        except Exception as e:
            logger.error("Embedding generation failed: %s", e)
            raise EmbeddingError(f"Embedding generation failed: {e}") from e

    def generate_query_embedding(self, query: str) -> np.ndarray:
        """
        Generate a unit-normalized embedding vector for a single search query string.
        """
        if not query or not query.strip():
            raise InvalidVectorError("Cannot generate embedding for an empty query.")

        self._load_model()

        try:
            raw_embedding = self._model.encode(  # type: ignore
                query.strip(),
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=False,
            )
            raw_2d = np.atleast_2d(np.asarray(raw_embedding, dtype=np.float32))
            return self.normalize_vectors(raw_2d)

        except InvalidVectorError:
            raise
        except Exception as e:
            logger.error("Query embedding generation failed: %s", e)
            raise EmbeddingError(f"Query embedding generation failed: {e}") from e
