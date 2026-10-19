"""Unit tests for FAISSVectorStore: indexing, cosine scoring, persistence, and integrity."""

import os
from pathlib import Path
import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.user import User
from app.rag.embeddings.mock_embedding import MockEmbeddingService
from app.rag.vector_store.faiss_store import (
    DimensionMismatchError,
    FAISSVectorStore,
    IndexCorruptedError,
    PathTraversalError,
    validate_index_path,
)


def test_faiss_store_initialization_and_empty_search(tmp_path: Path):
    """Verify fresh FAISS store starts with 0 vectors and returns empty search."""
    index_file = tmp_path / "test.index"
    store = FAISSVectorStore(dimension=16, index_path=str(index_file), auto_load=True)

    assert store.dimension == 16
    assert store.ntotal == 0

    q = np.random.randn(1, 16).astype(np.float32)
    q = q / np.linalg.norm(q)

    # Empty candidate list returns empty
    results = store.search_prefiltered(q, top_k=5, allowed_vector_ids=[])
    assert results == []

    # Non-empty candidate list against empty index returns empty
    results = store.search_prefiltered(q, top_k=5, allowed_vector_ids=[1, 2])
    assert results == []


def test_faiss_store_add_and_cosine_similarity_ordering(tmp_path: Path):
    """Verify vectors are retrieved in exact cosine similarity order."""
    index_file = tmp_path / "test.index"
    store = FAISSVectorStore(dimension=4, index_path=str(index_file), auto_load=True)

    # Unit vectors
    v1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)  # Distance 1.0 to query
    v2 = np.array([0.7071, 0.7071, 0.0, 0.0], dtype=np.float32)  # Distance ~0.707
    v3 = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)  # Distance 0.0
    vectors = np.vstack([v1, v2, v3])
    vector_ids = [101, 102, 103]

    added = store.add_vectors(vector_ids, vectors, persist=True)
    assert added == 3
    assert store.ntotal == 3

    # Query matches v1 exactly
    q = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    hits = store.search_prefiltered(
        query_vector=q,
        top_k=3,
        allowed_vector_ids=[101, 102, 103],
        threshold=0.0,
    )

    assert len(hits) == 3
    # Top match must be 101 with score ~1.0
    assert hits[0][0] == 101
    assert np.isclose(hits[0][1], 1.0, atol=1e-4)
    # Second match is 102 with score ~0.707
    assert hits[1][0] == 102
    assert np.isclose(hits[1][1], 0.7071, atol=1e-3)
    # Third match is 103 with score 0.0
    assert hits[2][0] == 103
    assert np.isclose(hits[2][1], 0.0, atol=1e-4)


def test_faiss_store_idempotency_prevents_duplicate_vectors(tmp_path: Path):
    """Verify re-indexing the same vector IDs updates them without creating duplicate entries."""
    index_file = tmp_path / "test.index"
    store = FAISSVectorStore(dimension=4, index_path=str(index_file), auto_load=True)

    v = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    store.add_vectors([55], v, persist=True)
    assert store.ntotal == 1

    # Re-add with same ID
    v_updated = np.array([[0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    store.add_vectors([55], v_updated, persist=True)
    # Total vectors must remain 1, not 2
    assert store.ntotal == 1

    # Verify query for updated vector gets score 1.0
    q = np.array([[0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    hits = store.search_prefiltered(q, top_k=1, allowed_vector_ids=[55])
    assert hits[0][0] == 55
    assert np.isclose(hits[0][1], 1.0, atol=1e-4)


def test_faiss_store_remove_vectors(tmp_path: Path):
    """Verify removing vectors updates index and excludes them from search."""
    index_file = tmp_path / "test.index"
    store = FAISSVectorStore(dimension=4, index_path=str(index_file), auto_load=True)

    v = np.eye(3, 4, dtype=np.float32)
    store.add_vectors([1, 2, 3], v, persist=True)
    assert store.ntotal == 3

    # Remove vector 2
    removed = store.remove_vectors([2], persist=True)
    assert removed == 1
    assert store.ntotal == 2

    # Vector 2 is no longer retrievable
    q = v[1:2]
    hits = store.search_prefiltered(q, top_k=3, allowed_vector_ids=[1, 2, 3])
    hit_ids = [vid for vid, _ in hits]
    assert 2 not in hit_ids


def test_faiss_store_persistence_and_reload(tmp_path: Path):
    """Verify FAISS index is saved to disk and can be reloaded with intact vectors."""
    index_file = tmp_path / "test.index"
    store = FAISSVectorStore(dimension=4, index_path=str(index_file), auto_load=True)

    v = np.eye(2, 4, dtype=np.float32)
    store.add_vectors([10, 20], v, persist=True)
    assert index_file.exists()

    # Load in new store instance pointing to same file
    store2 = FAISSVectorStore(dimension=4, index_path=str(index_file), auto_load=True)
    assert store2.ntotal == 2

    q = v[0:1]
    hits = store2.search_prefiltered(q, top_k=1, allowed_vector_ids=[10])
    assert hits[0][0] == 10


def test_faiss_store_corrupted_file_detection(tmp_path: Path):
    """Verify corrupted index file raises IndexCorruptedError."""
    corrupted_file = tmp_path / "corrupted.index"
    with open(corrupted_file, "wb") as f:
        f.write(b"NOT_A_FAISS_INDEX_BINARY_DATA_CORRUPT")

    with pytest.raises(IndexCorruptedError):
        FAISSVectorStore(dimension=4, index_path=str(corrupted_file), auto_load=True)


def test_faiss_store_dimension_mismatch_detection(tmp_path: Path):
    """Verify mismatch between index dimension and vectors raises DimensionMismatchError."""
    index_file = tmp_path / "dim_test.index"
    store = FAISSVectorStore(dimension=8, index_path=str(index_file), auto_load=True)

    wrong_dim_vectors = np.ones((1, 4), dtype=np.float32)
    with pytest.raises(DimensionMismatchError):
        store.add_vectors([1], wrong_dim_vectors)

    wrong_dim_query = np.ones((1, 16), dtype=np.float32)
    with pytest.raises(DimensionMismatchError):
        store.search_prefiltered(wrong_dim_query, top_k=1, allowed_vector_ids=[1])


def test_faiss_store_path_traversal_prevention(tmp_path: Path):
    """Verify paths escaping the configured index directory are rejected."""
    # Temporarily set configured root
    original_path = settings.FAISS_INDEX_PATH
    settings.FAISS_INDEX_PATH = str(tmp_path / "indices" / "default.index")
    try:
        escaped_path = tmp_path / "other_folder" / "escaped.index"
        with pytest.raises(PathTraversalError):
            validate_index_path(escaped_path)
    finally:
        settings.FAISS_INDEX_PATH = original_path


def test_faiss_store_rebuild_from_db(
    tmp_path: Path, db_session: Session, sample_document: Document
):
    """Verify rebuild_from_db reconstructs index from ground-truth database records."""
    # Create chunks for sample_document
    chunk1 = DocumentChunk(
        document_id=sample_document.id,
        vector_id=1001,
        chunk_index=0,
        content="Rebuilt chunk 1 content.",
        token_count=5,
    )
    chunk2 = DocumentChunk(
        document_id=sample_document.id,
        vector_id=1002,
        chunk_index=1,
        content="Rebuilt chunk 2 content.",
        token_count=5,
    )
    db_session.add_all([chunk1, chunk2])
    db_session.commit()

    index_file = tmp_path / "rebuild.index"
    store = FAISSVectorStore(dimension=64, index_path=str(index_file), auto_load=True)
    assert store.ntotal == 0

    mock_emb = MockEmbeddingService(dimension=64)
    total_rebuilt = store.rebuild_from_db(db_session, mock_emb)

    assert total_rebuilt == 2
    assert store.ntotal == 2

    # Query matching chunk 1
    q = mock_emb.generate_query_embedding("Rebuilt chunk 1 content.")
    hits = store.search_prefiltered(q, top_k=1, allowed_vector_ids=[1001, 1002])
    assert hits[0][0] == 1001
