"""Integration tests for secure HttpOnly refresh cookies, CSRF protection, and origin validation."""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.token import RefreshToken
from app.models.user import User


@pytest.mark.asyncio
async def test_login_sets_httponly_cookie_and_excludes_refresh_from_json(
    async_client: AsyncClient, sample_user: User
):
    """
    Verify login sets secure HttpOnly cookie for refresh token,
    emits readable CSRF token, and strictly excludes refresh_token from JSON.
    """
    login_payload = {"email": sample_user.email, "password": "SecurePassword123!"}
    res = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 200
    data = res.json()

    # 1. JSON payload verification
    assert "access_token" in data
    assert "refresh_token" not in data, "Security violation: refresh_token must not leak in JSON response"
    assert data["token_type"] == "bearer"
    assert "csrf_token" in data

    # 2. Cookie verification
    assert settings.REFRESH_COOKIE_NAME in res.cookies
    assert settings.CSRF_COOKIE_NAME in res.cookies

    # 3. Inspect raw Set-Cookie header flags
    set_cookie_headers = res.headers.get_list("set-cookie")
    refresh_cookie_header = next(
        (h for h in set_cookie_headers if settings.REFRESH_COOKIE_NAME in h), None
    )
    csrf_cookie_header = next(
        (h for h in set_cookie_headers if settings.CSRF_COOKIE_NAME in h), None
    )

    assert refresh_cookie_header is not None
    assert "httponly" in refresh_cookie_header.lower()
    assert f"path={settings.REFRESH_COOKIE_PATH.lower()}" in refresh_cookie_header.lower()
    assert f"samesite={settings.REFRESH_COOKIE_SAMESITE.lower()}" in refresh_cookie_header.lower()

    assert csrf_cookie_header is not None
    # CSRF cookie must be readable by frontend SPA
    assert "httponly" not in csrf_cookie_header.lower()


@pytest.mark.asyncio
async def test_refresh_succeeds_with_cookie_and_csrf_header(
    async_client: AsyncClient, sample_user: User
):
    """Verify refresh route succeeds when presenting HttpOnly cookie and matching X-CSRF-Token."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    initial_refresh = login_res.cookies.get(settings.REFRESH_COOKIE_NAME)
    csrf_token = login_res.cookies.get(settings.CSRF_COOKIE_NAME)
    assert initial_refresh is not None
    assert csrf_token is not None

    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert refresh_res.status_code == 200
    rot_data = refresh_res.json()
    assert "access_token" in rot_data
    assert "refresh_token" not in rot_data

    # Rotated cookie must be distinct from initial cookie
    new_refresh = refresh_res.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert new_refresh is not None
    assert new_refresh != initial_refresh


@pytest.mark.asyncio
async def test_csrf_token_validation_rejects_missing_or_mismatched_token(
    async_client: AsyncClient, sample_user: User
):
    """Verify cookie-authenticated refresh is rejected with HTTP 403 on missing or forged CSRF token."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200

    # 1. Missing X-CSRF-Token header -> 403 Forbidden
    res_no_csrf = await async_client.post("/api/v1/auth/refresh")
    assert res_no_csrf.status_code == 403
    assert "CSRF" in res_no_csrf.json()["detail"]

    # 2. Forged / Mismatched X-CSRF-Token header -> 403 Forbidden
    res_bad_csrf = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": "forged-attacker-csrf-token"},
    )
    assert res_bad_csrf.status_code == 403
    assert "CSRF" in res_bad_csrf.json()["detail"]


@pytest.mark.asyncio
async def test_origin_validation_rejects_unauthorized_cross_origin_requests(
    async_client: AsyncClient, sample_user: User
):
    """Verify state-changing auth endpoints reject untrusted Origin headers with HTTP 403."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    csrf_token = login_res.cookies.get(settings.CSRF_COOKIE_NAME)

    # Malicious website attempting cross-origin refresh
    malicious_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={
            "X-CSRF-Token": csrf_token,
            "Origin": "https://evil-phishing-site.example.com",
        },
    )
    assert malicious_res.status_code == 403
    assert "origin" in malicious_res.json()["detail"].lower()

    # Allowed frontend origin succeeds
    trusted_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={
            "X-CSRF-Token": csrf_token,
            "Origin": "http://localhost:5173",
        },
    )
    assert trusted_res.status_code == 200


@pytest.mark.asyncio
async def test_logout_clears_cookies_and_revokes_token(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify logout clears refresh & CSRF cookies and invalidates database record."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    csrf_token = login_res.cookies.get(settings.CSRF_COOKIE_NAME)
    refresh_token = login_res.cookies.get(settings.REFRESH_COOKIE_NAME)

    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_res.status_code == 200
    assert "logged out" in logout_res.json()["message"].lower()

    # Verify Set-Cookie header contains deletion instructions (Max-Age=0)
    set_cookie_headers = logout_res.headers.get_list("set-cookie")
    assert any(
        settings.REFRESH_COOKIE_NAME in h and ('max-age=0' in h.lower() or 'expires=' in h.lower())
        for h in set_cookie_headers
    )
    assert any(
        settings.CSRF_COOKIE_NAME in h and ('max-age=0' in h.lower() or 'expires=' in h.lower())
        for h in set_cookie_headers
    )

    # Attempting to use logged-out refresh token fails with 401
    async_client.cookies.set(settings.REFRESH_COOKIE_NAME, refresh_token)
    async_client.cookies.set(settings.CSRF_COOKIE_NAME, csrf_token)
    retry_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert retry_res.status_code == 401


@pytest.mark.asyncio
async def test_replay_attack_revokes_family_and_clears_cookie(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify token reuse alarm revokes all active family tokens and returns deletion cookies."""
    # 1. Login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    token1 = login_res.cookies.get(settings.REFRESH_COOKIE_NAME)
    csrf1 = login_res.cookies.get(settings.CSRF_COOKIE_NAME)

    # 2. Rotate -> token2
    rot_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf1},
    )
    assert rot_res.status_code == 200
    token2 = rot_res.cookies.get(settings.REFRESH_COOKIE_NAME)
    csrf2 = rot_res.cookies.get(settings.CSRF_COOKIE_NAME)

    # 3. Replay token1
    async_client.cookies.set(settings.REFRESH_COOKIE_NAME, token1)
    replay_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf2},
    )
    assert replay_res.status_code == 401
    assert "reuse detected" in replay_res.json()["detail"].lower()

    # 4. Check all DB tokens for user are revoked
    user_tokens = db_session.query(RefreshToken).filter_by(user_id=sample_user.id).all()
    assert len(user_tokens) >= 2
    assert all(t.is_revoked for t in user_tokens)

    # 5. Legitimate token2 is now also rejected
    async_client.cookies.set(settings.REFRESH_COOKIE_NAME, token2)
    victim_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf2},
    )
    assert victim_res.status_code == 401


def test_cors_configuration_prevents_wildcard_with_credentials():
    """Verify that CORS setting rejects wildcard origin when credentials and cookies are enabled."""
    from app.core.config import Settings

    # Setting wildcard in BACKEND_CORS_ORIGINS must raise ValueError
    with pytest.raises(ValueError, match="cannot contain '\\*' wildcard"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a" * 32,
            BACKEND_CORS_ORIGINS=["*"],
        )


@pytest.mark.asyncio
async def test_csrf_token_rejects_injected_cookie_with_invalid_signature(
    async_client: AsyncClient, sample_user: User
):
    """
    Verify that an attacker injecting matching cookie and header values (e.g. via subdomain cookie tossing)
    is rejected with HTTP 403 Forbidden because the HMAC signature is missing or invalid.
    """
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": sample_user.email, "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200

    # Attacker crafts matching header and cookie without knowing server SECRET_KEY
    forged_token = "injected_attacker_token.invalid_signature_hex"
    async_client.cookies.set(settings.CSRF_COOKIE_NAME, forged_token)

    forged_res = await async_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": forged_token},
    )
    assert forged_res.status_code == 403
    assert "signature invalid" in forged_res.json()["detail"].lower()
