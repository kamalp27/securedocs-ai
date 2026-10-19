"""Unit tests for embedding services: dimensions, normalization, error handling."""

import numpy as np
import pytest

from app.rag.embeddings.base import (
    BaseEmbeddingService,
    EmbeddingError,
    InvalidVectorError,
    ModelLoadError,
)
from app.rag.embeddings.mock_embedding import MockEmbeddingService
from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingService


def test_mock_embedding_dimension_and_shape():
    """Verify mock embedding generator returns expected shapes and dimensions."""
    svc = MockEmbeddingService(dimension=128)
    assert svc.dimension == 128

    texts = ["First chunk of text.", "Second chunk of text.", "Third chunk."]
    embeddings = svc.generate_embeddings(texts)

    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (3, 128)
    assert embeddings.dtype == np.float32


def test_mock_embedding_l2_normalization():
    """Verify all generated vectors are L2-normalized to unit length (norm == 1.0)."""
    svc = MockEmbeddingService(dimension=64)
    embeddings = svc.generate_embeddings(["SecureDocs AI architecture", "PostgreSQL database"])

    norms = np.linalg.norm(embeddings, axis=1)
    for norm in norms:
        assert np.isclose(norm, 1.0, atol=1e-5)


def test_mock_embedding_query_shape_and_normalization():
    """Verify single query embedding returns shape (1, d) and unit length."""
    svc = MockEmbeddingService(dimension=384)
    q_vec = svc.generate_query_embedding("Search query text")

    assert q_vec.shape == (1, 384)
    norm = np.linalg.norm(q_vec)
    assert np.isclose(norm, 1.0, atol=1e-5)


def test_mock_embedding_deterministic_output():
    """Verify identical text produces identical embeddings."""
    svc = MockEmbeddingService(dimension=128)
    t = "Deterministic repeatable text sequence."

    v1 = svc.generate_query_embedding(t)
    v2 = svc.generate_query_embedding(t)
    np.testing.assert_array_almost_equal(v1, v2)


def test_mock_embedding_empty_text_rejected():
    """Verify empty text strings raise InvalidVectorError."""
    svc = MockEmbeddingService(dimension=64)
    with pytest.raises(InvalidVectorError):
        svc.generate_query_embedding("")

    with pytest.raises(InvalidVectorError):
        svc.generate_query_embedding("   ")

    with pytest.raises(InvalidVectorError):
        svc.generate_embeddings(["Valid text", "   "])


def test_base_normalize_vectors_finite_check():
    """Verify non-finite vectors (NaN or Inf) are rejected."""
    bad_vectors_nan = np.array([[1.0, np.nan, 0.0]], dtype=np.float32)
    with pytest.raises(InvalidVectorError, match="non-finite"):
        BaseEmbeddingService.normalize_vectors(bad_vectors_nan)

    bad_vectors_inf = np.array([[1.0, np.inf, 0.0]], dtype=np.float32)
    with pytest.raises(InvalidVectorError, match="non-finite"):
        BaseEmbeddingService.normalize_vectors(bad_vectors_inf)


def test_base_normalize_vectors_zero_norm_rejected():
    """Verify all-zero vectors are rejected."""
    zero_vector = np.array([[0.0, 0.0, 0.0]], dtype=np.float32)
    with pytest.raises(InvalidVectorError, match="zero-magnitude"):
        BaseEmbeddingService.normalize_vectors(zero_vector)


def test_sentence_transformer_lazy_load_failure_handling(monkeypatch):
    """Verify clear ModelLoadError if model weights cannot be loaded."""
    def fail_load(*args, **kwargs):
        raise RuntimeError("Network offline and model not in local cache")

    svc = SentenceTransformerEmbeddingService(model_name="non-existent-model-xyz")
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", fail_load)

    with pytest.raises(ModelLoadError, match="Could not load embedding model"):
        _ = svc.dimension
