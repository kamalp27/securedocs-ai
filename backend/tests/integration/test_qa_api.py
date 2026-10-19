"""Integration tests for Grounded Generative Q&A API: multi-tenant authorization, citations, and evidence checks."""

import io
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_password_hash
from app.models.audit import AuditLog
from app.models.permission import DocumentPermission
from app.models.user import User


@pytest.fixture
def other_user(db_session: Session) -> User:
    """Fixture providing a second distinct user for multi-tenant isolation tests."""
    user = User(
        id=uuid.uuid4(),
        email="qa_analyst_2@securedocs.io",
        hashed_password=get_password_hash("OtherUserSecret123!"),
        full_name="Second Analyst",
        role="analyst",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_qa_unauthenticated_rejected(async_client: AsyncClient):
    """Verify unauthenticated Q&A requests receive HTTP 401."""
    payload = {"question": "What is the company password policy?"}
    response = await async_client.post("/api/v1/qa/ask", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_qa_empty_corpus_insufficient_evidence(
    async_client: AsyncClient, sample_user: User
):
    """Verify querying an empty document corpus returns insufficient evidence safely."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"question": "What is our Disaster Recovery RPO target?"}
    response = await async_client.post("/api/v1/qa/ask", headers=headers, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "What is our Disaster Recovery RPO target?"
    assert data["insufficient_evidence"] is True
    assert "insufficient evidence" in data["answer"].lower()
    assert data["citations"] == []
    assert data["retrieved_chunk_count"] == 0
    assert data["retrieved_chunks"] == []


@pytest.mark.asyncio
async def test_qa_ask_own_document_success(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify an authenticated user can ask questions and receive grounded answers with citations."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Upload document
    doc_text = (
        "Enterprise IT Infrastructure Guidelines 2026.\n\n"
        "Disaster Recovery protocols mandate a Recovery Point Objective of 15 minutes.\n\n"
        "The primary database cluster replicates asynchronously to an off-site region."
    )
    files = {"file": ("dr_policy.txt", io.BytesIO(doc_text.encode("utf-8")), "text/plain")}
    up_res = await async_client.post(
        "/api/v1/documents/upload", headers=headers, files=files, data={"classification": "internal"}
    )
    assert up_res.status_code == 201
    doc_id = up_res.json()["id"]

    # Submit Q&A request
    payload = {
        "question": "What is the Recovery Point Objective mandate?",
        "top_k": 3,
        "similarity_threshold": 0.0,
    }
    qa_res = await async_client.post("/api/v1/qa/ask", headers=headers, json=payload)

    assert qa_res.status_code == 200
    res_data = qa_res.json()

    assert res_data["insufficient_evidence"] is False
    assert "15 minutes" in res_data["answer"]
    assert res_data["retrieved_chunk_count"] >= 1

    # Verify citation structure and authenticity
    assert len(res_data["citations"]) >= 1
    top_citation = res_data["citations"][0]
    assert top_citation["document_id"] == doc_id
    assert top_citation["original_filename"] == "dr_policy.txt"
    assert top_citation["quoted_snippet"] is not None
    assert "15 minutes" in top_citation["quoted_snippet"]

    # Verify diagnostic chunks
    assert len(res_data["retrieved_chunks"]) >= 1
    assert res_data["retrieved_chunks"][0]["document_id"] == doc_id


@pytest.mark.asyncio
async def test_qa_multi_tenant_authorization_isolation(
    async_client: AsyncClient,
    sample_user: User,
    other_user: User,
    db_session: Session,
):
    """
    CRITICAL SECURITY TEST: Multi-tenant boundary enforcement.
    User A uploads a confidential document.
    User B MUST NOT be able to extract answers or receive citations from User A's document.
    """
    token_a = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    token_b = create_access_token(subject=other_user.id, role=other_user.role)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A uploads confidential document
    secret_text = "Project Falcon Alpha total Q4 budget is allocated at 18 million dollars."
    files = {"file": ("falcon_secret.txt", io.BytesIO(secret_text.encode("utf-8")), "text/plain")}
    up_res = await async_client.post(
        "/api/v1/documents/upload", headers=headers_a, files=files, data={"classification": "confidential"}
    )
    assert up_res.status_code == 201

    # User B queries about Project Falcon Alpha budget
    query_payload = {"question": "What is the total Q4 budget for Project Falcon Alpha?", "top_k": 5}
    user_b_res = await async_client.post("/api/v1/qa/ask", headers=headers_b, json=query_payload)

    assert user_b_res.status_code == 200
    user_b_data = user_b_res.json()

    # User B must be denied access: zero citations, zero chunks, insufficient evidence
    assert user_b_data["insufficient_evidence"] is True
    assert user_b_data["citations"] == []
    assert user_b_data["retrieved_chunk_count"] == 0
    assert "18 million" not in user_b_data["answer"]

    # In contrast, User A submits the identical query and succeeds
    user_a_res = await async_client.post("/api/v1/qa/ask", headers=headers_a, json=query_payload)
    assert user_a_res.status_code == 200
    user_a_data = user_a_res.json()

    assert user_a_data["insufficient_evidence"] is False
    assert "18 million" in user_a_data["answer"]
    assert len(user_a_data["citations"]) >= 1
    assert user_a_data["citations"][0]["original_filename"] == "falcon_secret.txt"


@pytest.mark.asyncio
async def test_qa_shared_permission_enables_cross_user_qa(
    async_client: AsyncClient,
    sample_user: User,
    other_user: User,
    db_session: Session,
):
    """
    Verify that when User A explicitly grants read permission to User B,
    User B can successfully query and cite the shared document.
    """
    token_a = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    token_b = create_access_token(subject=other_user.id, role=other_user.role)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A uploads a shared knowledge base
    kb_text = "Server patching takes place on the third Sunday of each calendar month at 02:00 UTC."
    files = {"file": ("maintenance.txt", io.BytesIO(kb_text.encode("utf-8")), "text/plain")}
    up_res = await async_client.post(
        "/api/v1/documents/upload", headers=headers_a, files=files, data={"classification": "internal"}
    )
    assert up_res.status_code == 201
    doc_id = uuid.UUID(up_res.json()["id"])

    # Grant read permission to User B
    perm = DocumentPermission(
        id=uuid.uuid4(),
        document_id=doc_id,
        user_id=other_user.id,
        permission_level="view",
    )
    db_session.add(perm)
    db_session.commit()

    # User B queries about server patching
    payload = {"question": "When does server patching take place?"}
    qa_res = await async_client.post("/api/v1/qa/ask", headers=headers_b, json=payload)

    assert qa_res.status_code == 200
    res_data = qa_res.json()
    assert res_data["insufficient_evidence"] is False
    assert "third Sunday" in res_data["answer"]
    assert len(res_data["citations"]) >= 1
    assert res_data["citations"][0]["document_id"] == str(doc_id)


@pytest.mark.asyncio
async def test_qa_audit_log_created(
    async_client: AsyncClient,
    sample_user: User,
    db_session: Session,
):
    """Verify Q&A query attempts create an immutable AuditLog record."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    question_text = "Audit probe query test for compliance verification?"
    payload = {"question": question_text}
    res = await async_client.post("/api/v1/qa/ask", headers=headers, json=payload)
    assert res.status_code == 200

    # Query audit logs
    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.user_id == sample_user.id, AuditLog.action == "qa_query")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit_entry is not None
    assert question_text in audit_entry.query_text
    assert audit_entry.status_code == 200


@pytest.mark.asyncio
async def test_qa_input_validation(async_client: AsyncClient, sample_user: User):
    """Verify input validation enforces question bounds."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Empty question
    res_empty = await async_client.post("/api/v1/qa/ask", headers=headers, json={"question": ""})
    assert res_empty.status_code == 422

    # Whitespace only
    res_ws = await async_client.post("/api/v1/qa/ask", headers=headers, json={"question": "   "})
    assert res_ws.status_code == 422

    # Exceeding 1000 characters
    res_long = await async_client.post(
        "/api/v1/qa/ask", headers=headers, json={"question": "x" * 1001}
    )
    assert res_long.status_code == 422

    # Invalid top_k
    res_topk = await async_client.post(
        "/api/v1/qa/ask", headers=headers, json={"question": "Valid?", "top_k": 0}
    )
    assert res_topk.status_code == 422


@pytest.mark.asyncio
async def test_qa_provider_selection_and_unknown_rejection(
    async_client: AsyncClient, sample_user: User
):
    """Verify explicit provider selection accepts valid names and rejects unknown names with HTTP 400."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Valid explicit provider
    res_valid = await async_client.post(
        "/api/v1/qa/ask",
        headers=headers,
        json={"question": "What is the policy?", "provider": "deterministic_extractive"},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["provider"] == "deterministic_extractive"

    # Unknown provider
    res_unknown = await async_client.post(
        "/api/v1/qa/ask",
        headers=headers,
        json={"question": "What is the policy?", "provider": "unsupported_cloud_api"},
    )
    assert res_unknown.status_code == 400
    assert "Unsupported generator provider" in res_unknown.json()["detail"]


@pytest.mark.asyncio
async def test_qa_ollama_unavailable_returns_503_safe_error(
    async_client: AsyncClient, sample_user: User, monkeypatch
):
    """
    Verify selecting Ollama when the local daemon is unreachable returns HTTP 503
    with a safe error message and zero leaked stack traces or paths.
    """
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Point to an unreachable port to guarantee connection failure
    monkeypatch.setattr("app.core.config.settings.OLLAMA_BASE_URL", "http://127.0.0.1:59999")
    monkeypatch.setattr("app.core.config.settings.OLLAMA_FALLBACK_TO_EXTRACTIVE", False)

    # First upload a document so retrieval produces chunks and calls generator
    text = "Database connection pool size is configured at 20 max overflow."
    files = {"file": ("db_pool.txt", io.BytesIO(text.encode("utf-8")), "text/plain")}
    await async_client.post(
        "/api/v1/documents/upload", headers=headers, files=files, data={"classification": "internal"}
    )

    res = await async_client.post(
        "/api/v1/qa/ask",
        headers=headers,
        json={"question": "What is the connection pool size?", "provider": "ollama"},
    )

    assert res.status_code == 503
    detail = res.json()["detail"]
    assert "currently unavailable" in detail.lower()
    # Confirm no tracebacks or internal file paths in response
    assert "Traceback" not in detail
    assert "securedocs" not in detail.lower()

