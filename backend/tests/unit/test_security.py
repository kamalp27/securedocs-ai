"""Unit tests for password hashing and JWT token operations."""

import uuid
from datetime import timedelta
import pytest

from app.core.security import (
    InvalidTokenTypeError,
    TokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    hash_token,
    verify_password,
)


def test_password_hashing_and_verification():
    """Verify that Argon2id generates valid hashes and correctly validates passwords."""
    password = "SuperSecretPassword123!"
    hashed = get_password_hash(password)

    # Must be Argon2id format and not plaintext
    assert hashed != password
    assert "$argon2id$" in hashed
    assert len(hashed) > 40

    # Verification
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_token_hash_is_sha256_deterministic():
    """Verify that hash_token computes consistent SHA-256 hex string."""
    token = "some_random_jwt_or_uuid_string"
    h1 = hash_token(token)
    h2 = hash_token(token)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex length
    assert h1 != token


def test_create_and_decode_access_token():
    """Verify access token creation, payload fields, and type enforcement."""
    user_id = uuid.uuid4()
    token = create_access_token(subject=user_id, role="manager")

    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "manager"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_create_and_decode_refresh_token():
    """Verify refresh token creation, hashing, and type verification."""
    user_id = uuid.uuid4()
    raw_token, token_hash, expires_at = create_refresh_token(subject=user_id)

    assert len(token_hash) == 64
    payload = decode_token(raw_token, expected_type="refresh")
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "refresh"


def test_token_type_mismatch_raises_error():
    """Verify that an access token cannot be decoded as a refresh token and vice-versa."""
    user_id = uuid.uuid4()
    access_token = create_access_token(subject=user_id, role="analyst")

    with pytest.raises(InvalidTokenTypeError):
        decode_token(access_token, expected_type="refresh")

    raw_refresh, _, _ = create_refresh_token(subject=user_id)
    with pytest.raises(InvalidTokenTypeError):
        decode_token(raw_refresh, expected_type="access")


def test_expired_token_raises_token_expired_error():
    """Verify that expired tokens raise TokenExpiredError."""
    user_id = uuid.uuid4()
    # Expired 10 seconds ago
    expired_token = create_access_token(
        subject=user_id,
        role="analyst",
        expires_delta=timedelta(seconds=-10),
    )

    with pytest.raises(TokenExpiredError):
        decode_token(expired_token)


def test_malformed_token_raises_token_error():
    """Verify that random strings or tampered tokens raise TokenError."""
    with pytest.raises(TokenError):
        decode_token("not.a.valid.jwt.token")
