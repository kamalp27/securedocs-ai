"""Integration tests for Authentication API endpoints and Authorization dependencies."""

import uuid
from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_refresh_token, get_password_hash
from app.models.token import RefreshToken
from app.models.user import User


@pytest.mark.asyncio
async def test_register_user_success(async_client: AsyncClient, db_session: Session):
    """Verify successful user registration with safe default role."""
    payload = {
        "email": "newuser@securedocs.io",
        "password": "StrongPassword123!",
        "full_name": "New User",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["email"] == "newuser@securedocs.io"
    assert data["full_name"] == "New User"
    assert data["role"] == "analyst"  # Safe default role
    assert data["is_active"] is True
    assert "password" not in data
    assert "hashed_password" not in data

    # Verify database state
    db_user = db_session.query(User).filter_by(email="newuser@securedocs.io").first()
    assert db_user is not None
    assert db_user.hashed_password != "StrongPassword123!"
    assert "$argon2id$" in db_user.hashed_password


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(async_client: AsyncClient, sample_user: User):
    """Verify that registering an existing email returns HTTP 409 Conflict."""
    payload = {
        "email": sample_user.email,
        "password": "AnotherPassword123!",
        "full_name": "Duplicate Attempt",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    data = response.json()
    assert "already exists" in data["detail"].lower()


@pytest.mark.asyncio
async def test_register_client_cannot_self_elevate_to_admin(
    async_client: AsyncClient, db_session: Session
):
    """Verify that clients sending role='admin' in payload are not granted admin role."""
    payload = {
        "email": "hacker@securedocs.io",
        "password": "Password1234!",
        "full_name": "Privilege Escalation Attempt",
        "role": "admin",  # Attempted privilege escalation
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "analyst"  # Default analyst, not admin

    db_user = db_session.query(User).filter_by(email="hacker@securedocs.io").first()
    assert db_user.role == "analyst"


@pytest.mark.asyncio
async def test_login_success_and_wrong_password(
    async_client: AsyncClient, sample_user: User
):
    """Verify login success returns token pair, and wrong password returns generic 401."""
    # 1. Correct password
    login_payload = {
        "email": sample_user.email,
        "password": "SecurePassword123!",
    }
    response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    assert "securedocs_refresh_token" in response.cookies
    assert "securedocs_csrf_token" in response.cookies
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0

    # 2. Incorrect password returns generic message
    wrong_payload = {
        "email": sample_user.email,
        "password": "WrongPassword999!",
    }
    fail_response = await async_client.post("/api/v1/auth/login", json=wrong_payload)
    assert fail_response.status_code == 401
    assert "incorrect email or password" in fail_response.json()["detail"].lower()

    # 3. Non-existent email returns same generic message (anti-enumeration)
    non_existent_payload = {
        "email": "ghost@doesnotexist.io",
        "password": "SomePassword123!",
    }
    ghost_response = await async_client.post("/api/v1/auth/login", json=non_existent_payload)
    assert ghost_response.status_code == 401
    assert ghost_response.json()["detail"] == fail_response.json()["detail"]


@pytest.mark.asyncio
async def test_get_current_user_profile_me(
    async_client: AsyncClient, sample_user: User
):
    """Verify /me returns authenticated user's profile with valid token."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_user.id)
    assert data["email"] == sample_user.email
    assert data["role"] == sample_user.role
    assert "password" not in data


@pytest.mark.asyncio
async def test_protected_routes_token_validation(
    async_client: AsyncClient, sample_user: User
):
    """Verify protected routes reject missing, malformed, expired, and wrong-type tokens."""
    # 1. Missing token
    res_missing = await async_client.get("/api/v1/auth/me")
    assert res_missing.status_code == 401

    # 2. Malformed token
    res_malformed = await async_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-valid-token"}
    )
    assert res_malformed.status_code == 401

    # 3. Expired token
    expired_token = create_access_token(
        subject=sample_user.id,
        role=sample_user.role,
        expires_delta=timedelta(seconds=-10),
    )
    res_expired = await async_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res_expired.status_code == 401

    # 4. Wrong-type token (refresh token presented as access token)
    raw_refresh, _, _ = create_refresh_token(subject=sample_user.id)
    res_wrong_type = await async_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {raw_refresh}"}
    )
    assert res_wrong_type.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_revocation(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify refresh token rotation issues new pair, invalidates old token, and rejects replay."""
    # Login to obtain initial cookies
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200
    assert "refresh_token" not in login_res.json()
    initial_refresh = login_res.cookies.get("securedocs_refresh_token")
    csrf_token = login_res.cookies.get("securedocs_csrf_token")
    assert initial_refresh is not None
    assert csrf_token is not None

    # First rotation: should succeed using cookie and X-CSRF-Token
    rot_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert rot_res.status_code == 200
    rot_data = rot_res.json()
    assert "refresh_token" not in rot_data
    new_refresh = rot_res.cookies.get("securedocs_refresh_token")
    new_csrf = rot_res.cookies.get("securedocs_csrf_token")
    assert new_refresh != initial_refresh

    # Verify old token is marked revoked in DB
    records = db_session.query(RefreshToken).filter_by(user_id=sample_user.id).all()
    assert len(records) == 2
    revoked_count = sum(1 for r in records if r.is_revoked)
    assert revoked_count == 1

    # Second attempt with OLD initial_refresh (Replay Attack): must be rejected
    async_client.cookies.set("securedocs_refresh_token", initial_refresh)
    replay_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": new_csrf or csrf_token},
    )
    assert replay_res.status_code == 401
    assert "reuse detected" in replay_res.json()["detail"].lower()

    # Due to replay detection, all active tokens for this user must now be revoked
    records_after_replay = db_session.query(RefreshToken).filter_by(user_id=sample_user.id).all()
    assert all(r.is_revoked for r in records_after_replay)

    # Trying to use new_refresh now should also fail because it was invalidated by the replay alarm
    async_client.cookies.set("securedocs_refresh_token", new_refresh)
    invalid_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": new_csrf or csrf_token},
    )
    assert invalid_res.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalidates_refresh_token(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify logout revokes the presented refresh token and clears cookies."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    csrf_token = login_res.cookies.get("securedocs_csrf_token")
    old_refresh = login_res.cookies.get("securedocs_refresh_token")
    assert csrf_token is not None
    assert old_refresh is not None

    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_res.status_code == 200
    assert "logged out" in logout_res.json()["message"].lower()

    # Attempting to refresh with the logged-out token must fail
    async_client.cookies.set("securedocs_refresh_token", old_refresh)
    async_client.cookies.set("securedocs_csrf_token", csrf_token)
    refresh_fail = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert refresh_fail.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_denied_login_and_access(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify that deactivating a user prevents login and blocks access to protected routes."""
    # Deactivate user
    sample_user.is_active = False
    db_session.commit()

    # Login attempt fails with 403
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 403
    assert "inactive" in login_res.json()["detail"].lower()

    # Protected route with previously issued token fails with 403
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    me_res = await async_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_res.status_code == 403
    assert "inactive" in me_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_role_protected_routes(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify role-protected endpoints accept authorized roles and reject unauthorized roles."""
    # sample_user is 'analyst'
    analyst_token = create_access_token(subject=sample_user.id, role="analyst")

    # Access admin ping with analyst token -> HTTP 403 Forbidden
    res_forbidden = await async_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert res_forbidden.status_code == 403
    assert "forbidden" in res_forbidden.json()["detail"].lower()

    # Create admin user
    admin_user = User(
        id=uuid.uuid4(),
        email="superadmin@securedocs.io",
        hashed_password=get_password_hash("AdminPass123!"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.commit()

    admin_token = create_access_token(subject=admin_user.id, role="admin")
    res_admin = await async_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["message"] == "Admin access granted"
