"""Security utilities: password hashing (Argon2id) and JWT token management."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple, Union

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

# Initialize password hasher with Argon2id (recommended modern standard)
pwd_hasher = PasswordHash.recommended()


class TokenError(Exception):
    """Base exception for JWT token processing errors."""
    pass


class TokenExpiredError(TokenError):
    """Raised when a JWT token has expired."""
    pass


class InvalidTokenTypeError(TokenError):
    """Raised when token type claim does not match expected type (e.g. refresh vs access)."""
    pass


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return pwd_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    return pwd_hasher.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """Compute SHA-256 hex digest of a token string for secure database persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    subject: Union[str, uuid.UUID],
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed, short-lived JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: Union[str, uuid.UUID],
    expires_delta: Optional[timedelta] = None,
) -> Tuple[str, str, datetime]:
    """
    Create a signed refresh token.
    Returns:
        (raw_token, token_hash, expires_at_datetime)
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    raw_jti = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": raw_jti,
    }
    raw_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash, expire


def decode_token(
    token: str,
    expected_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Decode and validate a JWT token signature, expiration, and type.
    Raises TokenExpiredError or TokenError on failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredError("Token has expired") from e
    except jwt.PyJWTError as e:
        raise TokenError(f"Invalid token: {e}") from e

    token_type = payload.get("type")
    if expected_type and token_type != expected_type:
        raise InvalidTokenTypeError(
            f"Invalid token type: expected '{expected_type}', got '{token_type}'"
        )

    return payload
