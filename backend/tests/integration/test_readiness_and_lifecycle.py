"""Integration tests for readiness probe, lifespan startup reconciliation, and security headers."""

import uuid
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.user import User
from app.rag.embeddings import get_embedding_service
from app.rag.vector_store import get_vector_store
from app.services.document_service import reconcile_index_if_needed


@pytest.mark.asyncio
async def test_root_liveness_and_readiness_healthy(async_client: AsyncClient):
    """Verify both /health and /health/ready return 200 when system is operational."""
    # 1. Liveness
    res_live = await async_client.get("/health")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "healthy"

    # 2. Readiness root
    res_ready = await async_client.get("/health/ready")
    assert res_ready.status_code == 200
    data = res_ready.json()
    assert data["status"] == "ready"
    assert data["components"]["database"] == "ok"
    assert data["components"]["vector_store"] == "ok"
    assert data["components"]["storage"] == "ok"

    # 3. Readiness API v1 path
    res_ready_v1 = await async_client.get("/api/v1/health/ready")
    assert res_ready_v1.status_code == 200


@pytest.mark.asyncio
async def test_readiness_fails_when_database_is_unavailable(async_client: AsyncClient):
    """Verify /health/ready returns HTTP 503 if the database is unreachable."""
    from app.main import app

    class FailingSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("Database connection timed out or pool exhausted.")

    original_override = app.dependency_overrides.get(get_db)

    def failing_db_override():
        yield FailingSession()

    app.dependency_overrides[get_db] = failing_db_override
    try:
        res = await async_client.get("/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "not_ready"
        assert data["components"]["database"] == "unavailable"

        # Also verify API v1 path returns 503
        res_v1 = await async_client.get("/api/v1/health/ready")
        assert res_v1.status_code == 503
        assert res_v1.json()["components"]["database"] == "unavailable"
    finally:
        if original_override is not None:
            app.dependency_overrides[get_db] = original_override
        else:
            app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_security_response_headers_present(async_client: AsyncClient):
    """Verify standard security headers are injected on HTTP responses."""
    res = await async_client.get("/health")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")


def test_startup_reconciliation_restores_empty_faiss_index(
    db_session: Session, sample_user: User
):
    """
    Verify reconcile_index_if_needed repopulates an empty FAISS index
    from indexed database chunks.
    """
    v_store = get_vector_store()
    emb_service = get_embedding_service()

    # 1. Clear vector index to simulate lost/empty index on disk
    v_store.clear()
    assert v_store.ntotal == 0

    # 2. Insert an indexed document with two chunks in database
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Reconciliation Spec.txt",
        original_filename="reconciliation.txt",
        storage_path="uploads/reconciliation.txt",
        mime_type="text/plain",
        file_size_bytes=1024,
        sha256_checksum="b" * 64,
        classification="internal",
        status="indexed",
        owner_id=sample_user.id,
    )
    db_session.add(doc)
    db_session.flush()

    chunk1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        vector_id=101,
        chunk_index=0,
        content="First paragraph of the critical system manual.",
        token_count=10,
    )
    chunk2 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        vector_id=102,
        chunk_index=1,
        content="Second paragraph detailing failover recovery steps.",
        token_count=10,
    )
    db_session.add_all([chunk1, chunk2])
    db_session.commit()

    # 3. Execute reconciliation
    rebuilt_count = reconcile_index_if_needed(
        db=db_session,
        embedding_service=emb_service,
        vector_store=v_store,
    )

    # 4. Verify vectors are restored
    assert rebuilt_count == 2
    assert v_store.ntotal == 2
