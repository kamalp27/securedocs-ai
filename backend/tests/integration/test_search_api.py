"""Integration tests for Search API: pre-retrieval authorization, multi-tenant boundaries, and input validation."""

import io
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_password_hash
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.permission import DocumentPermission
from app.models.user import User


@pytest.fixture
def other_user(db_session: Session) -> User:
    """Fixture providing a second distinct user for multi-tenant isolation tests."""
    user = User(
        id=uuid.uuid4(),
        email="other_analyst@securedocs.io",
        hashed_password=get_password_hash("OtherUserSecret123!"),
        full_name="Other User",
        role="analyst",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_search_unauthenticated_rejected(async_client: AsyncClient):
    """Verify unauthenticated search requests receive HTTP 401."""
    payload = {"query": "test query", "top_k": 5}
    response = await async_client.post("/api/v1/search", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_empty_corpus(async_client: AsyncClient, sample_user: User):
    """Verify searching with zero indexed documents returns empty results safely."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"query": "cloud infrastructure", "top_k": 5}
    response = await async_client.post("/api/v1/search", headers=headers, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "cloud infrastructure"
    assert data["total_results"] == 0
    assert data["results"] == []


@pytest.mark.asyncio
async def test_search_own_document_success(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify an authenticated user can upload and semantically search their own document."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Upload document
    text = (
        "FastAPI provides high performance asynchronous routing for modern APIs.\n\n"
        "SQLAlchemy 2.0 provides declarative typing and robust database connection pooling.\n\n"
        "FAISS CPU enables lightning-fast local vector similarity indexing."
    )
    files = {"file": ("tech_stack.txt", io.BytesIO(text.encode("utf-8")), "text/plain")}
    up_res = await async_client.post(
        "/api/v1/documents/upload", headers=headers, files=files, data={"classification": "internal"}
    )
    assert up_res.status_code == 201
    doc_id = up_res.json()["id"]

    # Search query
    payload = {"query": "FastAPI asynchronous routing", "top_k": 3}
    search_res = await async_client.post("/api/v1/search", headers=headers, json=payload)

    assert search_res.status_code == 200
    res_data = search_res.json()
    assert res_data["total_results"] >= 1

    top_hit = res_data["results"][0]
    assert top_hit["document_id"] == doc_id
    assert "FastAPI" in top_hit["content"]
    assert top_hit["original_filename"] == "tech_stack.txt"
    assert 0.0 <= top_hit["similarity_score"] <= 1.0


@pytest.mark.asyncio
async def test_search_multi_tenant_authorization_isolation(
    async_client: AsyncClient,
    sample_user: User,
    other_user: User,
    db_session: Session,
):
    """
    CRITICAL SECURITY TEST:
    Verify User A CANNOT retrieve User B's content even when User B's content is an exact match.
    Enforces that candidates are excluded before ranking.
    """
    token_a = create_access_token(subject=sample_user.id, role=sample_user.role)
    token_b = create_access_token(subject=other_user.id, role=other_user.role)

    # User A uploads innocuous marketing notes
    file_a = {"file": ("marketing.txt", io.BytesIO(b"Marketing strategies for quarterly public outreach."), "text/plain")}
    res_a = await async_client.post(
        "/api/v1/documents/upload", headers={"Authorization": f"Bearer {token_a}"}, files=file_a
    )
    assert res_a.status_code == 201

    # User B uploads highly confidential secret keys
    confidential_text = "CONFIDENTIAL ROOT CERTIFICATE PRIVATE KEY: 0x99AABBCCDDEEFF001122"
    file_b = {"file": ("vault_secrets.txt", io.BytesIO(confidential_text.encode("utf-8")), "text/plain")}
    res_b = await async_client.post(
        "/api/v1/documents/upload", headers={"Authorization": f"Bearer {token_b}"}, files=file_b
    )
    assert res_b.status_code == 201
    doc_b_id = res_b.json()["id"]

    # User A searches EXACTLY for User B's confidential secret keys
    query_leak_attempt = "CONFIDENTIAL ROOT CERTIFICATE PRIVATE KEY: 0x99AABBCCDDEEFF001122"
    search_payload = {"query": query_leak_attempt, "top_k": 5}

    res_user_a = await async_client.post(
        "/api/v1/search", headers={"Authorization": f"Bearer {token_a}"}, json=search_payload
    )
    assert res_user_a.status_code == 200
    user_a_results = res_user_a.json()["results"]

    # USER A MUST RECEIVE ZERO RESULTS MATCHING USER B'S DOCUMENT
    for item in user_a_results:
        assert item["document_id"] != doc_b_id
        assert "PRIVATE KEY" not in item["content"]

    # Verify User B CAN search and retrieve their own confidential document
    res_user_b = await async_client.post(
        "/api/v1/search", headers={"Authorization": f"Bearer {token_b}"}, json=search_payload
    )
    assert res_user_b.status_code == 200
    user_b_results = res_user_b.json()["results"]
    assert len(user_b_results) >= 1
    assert user_b_results[0]["document_id"] == doc_b_id
    assert "PRIVATE KEY" in user_b_results[0]["content"]


@pytest.mark.asyncio
async def test_search_deleted_document_removed_from_results(
    async_client: AsyncClient, sample_user: User
):
    """Verify deleting a document immediately removes it from semantic search results."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Upload document
    files = {"file": ("ephemeral.txt", io.BytesIO(b"Ephemeral financial records to be audited and discarded."), "text/plain")}
    up_res = await async_client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert up_res.status_code == 201
    doc_id = up_res.json()["id"]

    # Search finds it
    payload = {"query": "Ephemeral financial records", "top_k": 3}
    s1 = await async_client.post("/api/v1/search", headers=headers, json=payload)
    assert s1.status_code == 200
    assert s1.json()["total_results"] >= 1

    # Delete document
    del_res = await async_client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert del_res.status_code == 200

    # Search again: document is immediately gone
    s2 = await async_client.post("/api/v1/search", headers=headers, json=payload)
    assert s2.status_code == 200
    assert s2.json()["total_results"] == 0


@pytest.mark.asyncio
async def test_search_role_shared_document_access(
    async_client: AsyncClient, sample_user: User, other_user: User, db_session: Session
):
    """Verify documents shared with a user's role are accessible via search."""
    token_a = create_access_token(subject=sample_user.id, role=sample_user.role)
    token_b = create_access_token(subject=other_user.id, role=other_user.role)

    # User B uploads a document
    files = {"file": ("shared_policy.txt", io.BytesIO(b"Corporate compliance policy for all analysts."), "text/plain")}
    res_b = await async_client.post(
        "/api/v1/documents/upload", headers={"Authorization": f"Bearer {token_b}"}, files=files
    )
    assert res_b.status_code == 201
    doc_id = uuid.UUID(res_b.json()["id"])

    # Grant permission to role 'analyst' (which sample_user has)
    perm = DocumentPermission(
        document_id=doc_id,
        role_target="analyst",
        permission_level="view",
    )
    db_session.add(perm)
    db_session.commit()

    # User A searches for corporate compliance policy
    payload = {"query": "Corporate compliance policy", "top_k": 3}
    search_res = await async_client.post(
        "/api/v1/search", headers={"Authorization": f"Bearer {token_a}"}, json=payload
    )
    assert search_res.status_code == 200
    hits = search_res.json()["results"]
    assert len(hits) >= 1
    assert hits[0]["document_id"] == str(doc_id)


@pytest.mark.asyncio
async def test_search_input_validation(async_client: AsyncClient, sample_user: User):
    """Verify schema bounds on query length, top_k, and extra parameters."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Empty query rejected
    r1 = await async_client.post("/api/v1/search", headers=headers, json={"query": "   ", "top_k": 5})
    assert r1.status_code == 422

    # Query exceeding 1000 characters rejected
    r2 = await async_client.post("/api/v1/search", headers=headers, json={"query": "A" * 1001, "top_k": 5})
    assert r2.status_code == 422

    # top_k <= 0 rejected
    r3 = await async_client.post("/api/v1/search", headers=headers, json={"query": "valid query", "top_k": 0})
    assert r3.status_code == 422

    # top_k > 50 rejected
    r4 = await async_client.post("/api/v1/search", headers=headers, json={"query": "valid query", "top_k": 51})
    assert r4.status_code == 422

    # Extra parameters (e.g. attempting to inject owner_id) rejected by extra="forbid"
    r5 = await async_client.post(
        "/api/v1/search",
        headers=headers,
        json={"query": "valid", "top_k": 5, "owner_id": str(uuid.uuid4())},
    )
    assert r5.status_code == 422
