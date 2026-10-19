"""Integration tests for endpoint rate limiting, Retry-After headers, and identity isolation."""

import io
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.rate_limiter import limiter
from app.core.security import create_access_token, get_password_hash
from app.models.user import User


@pytest.fixture
def rate_limit_second_user(db_session: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="second_user_rl@securedocs.io",
        hashed_password=get_password_hash("Password123!"),
        full_name="Second User RL",
        role="analyst",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_auth_register_rate_limit_enforced(async_client: AsyncClient):
    """Verify POST /api/v1/auth/register allows 3 calls per minute, then returns HTTP 429."""
    limiter.reset()

    # Calls 1, 2, 3 succeed or return standard business responses (409 on duplicate, etc.)
    for i in range(3):
        res = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": f"user_rl_{i}@securedocs.io",
                "password": "Password123!",
                "full_name": f"User {i}",
            },
        )
        assert res.status_code == 201

    # 4th call must be blocked by rate limiter
    res_blocked = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "user_rl_blocked@securedocs.io",
            "password": "Password123!",
            "full_name": "Blocked User",
        },
    )
    assert res_blocked.status_code == 429
    assert "Too many requests" in res_blocked.json()["detail"]
    assert "Retry-After" in res_blocked.headers


@pytest.mark.asyncio
async def test_auth_login_rate_limit_enforced(async_client: AsyncClient, sample_user: User):
    """Verify POST /api/v1/auth/login allows 5 calls per minute, then returns HTTP 429."""
    limiter.reset()

    login_payload = {"email": sample_user.email, "password": "WrongPassword!"}

    # Calls 1 to 5 hit endpoint (returning 401 for wrong credentials)
    for _ in range(5):
        res = await async_client.post("/api/v1/auth/login", json=login_payload)
        assert res.status_code == 401

    # 6th call must be blocked by rate limiter with 429
    res_blocked = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert res_blocked.status_code == 429
    assert "Too many requests for login" in res_blocked.json()["detail"]
    assert int(res_blocked.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_document_upload_rate_limit_per_user(
    async_client: AsyncClient, sample_user: User, rate_limit_second_user: User
):
    """
    Verify POST /api/v1/documents/upload allows 10 calls per user, then returns HTTP 429.
    Verify User B is not blocked when User A exceeds rate limit (identity isolation).
    """
    limiter.reset()

    token_a = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    token_b = create_access_token(subject=rate_limit_second_user.id, role=rate_limit_second_user.role)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A uploads 10 documents
    for i in range(10):
        file_payload = {"file": (f"doc_{i}.txt", io.BytesIO(b"Valid test document text."), "text/plain")}
        res = await async_client.post("/api/v1/documents/upload", headers=headers_a, files=file_payload)
        assert res.status_code == 201

    # User A's 11th upload is blocked with 429
    file_11 = {"file": ("doc_11.txt", io.BytesIO(b"Valid text."), "text/plain")}
    res_blocked = await async_client.post("/api/v1/documents/upload", headers=headers_a, files=file_11)
    assert res_blocked.status_code == 429
    assert "Too many requests for document upload" in res_blocked.json()["detail"]

    # User B should NOT be blocked (identity isolation)
    file_b = {"file": ("doc_b.txt", io.BytesIO(b"User B text."), "text/plain")}
    res_b = await async_client.post("/api/v1/documents/upload", headers=headers_b, files=file_b)
    assert res_b.status_code == 201


@pytest.mark.asyncio
async def test_qa_ask_rate_limit_per_user(async_client: AsyncClient, sample_user: User):
    """Verify POST /api/v1/qa/ask allows 15 requests per minute, then returns HTTP 429."""
    limiter.reset()

    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    qa_payload = {"question": "What is the security policy?"}

    # Calls 1 to 15 succeed
    for _ in range(15):
        res = await async_client.post("/api/v1/qa/ask", headers=headers, json=qa_payload)
        assert res.status_code == 200

    # 16th call is blocked with 429
    res_blocked = await async_client.post("/api/v1/qa/ask", headers=headers, json=qa_payload)
    assert res_blocked.status_code == 429
    assert "Too many requests for Q&A query" in res_blocked.json()["detail"]
    assert "Retry-After" in res_blocked.headers
