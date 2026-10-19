"""Authentication and Token Management Service."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    hash_token,
    verify_password,
)
from app.models.token import RefreshToken
from app.models.user import User
from app.schemas.user import UserRegister


@dataclass
class TokenPairResult:
    """Internal token issuance container holding raw tokens for cookie/JSON routing."""
    access_token: str
    raw_refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class AuthError(Exception):
    """Base exception for authentication business errors."""
    pass


class UserAlreadyExistsError(AuthError):
    """Raised when registering an email that already exists."""
    pass


class InvalidCredentialsError(AuthError):
    """Raised when email/password verification fails."""
    pass


class InactiveUserError(AuthError):
    """Raised when an inactive user attempts to authenticate."""
    pass


class InvalidTokenServiceError(AuthError):
    """Raised when token validation or rotation fails."""
    pass


def register_user(db: Session, user_in: UserRegister) -> User:
    """Register a new user with safe default role and hashed password."""
    # Check for existing email (case-insensitive)
    existing_user = db.query(User).filter(User.email.ilike(user_in.email)).first()
    if existing_user:
        raise UserAlreadyExistsError("A user with this email address already exists.")

    hashed_pw = get_password_hash(user_in.password)
    user = User(
        id=uuid.uuid4(),
        email=user_in.email.lower().strip(),
        hashed_password=hashed_pw,
        full_name=user_in.full_name.strip() if user_in.full_name else None,
        role="analyst",  # Safe default role; client cannot self-elevate
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Verify credentials and return active user, or raise error."""
    user = db.query(User).filter(User.email.ilike(email)).first()
    if not user:
        # Generic message prevents email enumeration
        raise InvalidCredentialsError("Incorrect email or password.")

    if not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("Incorrect email or password.")

    if not user.is_active:
        raise InactiveUserError("User account is inactive. Please contact your administrator.")

    return user


def create_token_pair_for_user(db: Session, user: User) -> TokenPairResult:
    """Issue a new access token and persisted refresh token for user."""
    access_token = create_access_token(subject=user.id, role=user.role)
    raw_refresh_token, token_hash, expires_at = create_refresh_token(subject=user.id)

    refresh_record = RefreshToken(
        id=uuid.uuid4(),
        token_hash=token_hash,
        user_id=user.id,
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(refresh_record)
    db.commit()

    return TokenPairResult(
        access_token=access_token,
        raw_refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def rotate_refresh_token(db: Session, raw_refresh_token: str) -> TokenPairResult:
    """
    Validate, rotate, and reissue a refresh token pair.
    Detects token reuse: if a revoked token is presented, all user sessions are invalidated.
    """
    try:
        payload = decode_token(raw_refresh_token, expected_type="refresh")
    except TokenError as e:
        raise InvalidTokenServiceError(f"Invalid refresh token: {e}") from e

    token_hash = hash_token(raw_refresh_token)
    token_record = db.query(RefreshToken).filter_by(token_hash=token_hash).first()

    if not token_record:
        raise InvalidTokenServiceError("Refresh token not recognized.")

    # Token Reuse Detection (Replay Attack)
    if token_record.is_revoked:
        # Revoke all active tokens for this user family to protect account
        db.query(RefreshToken).filter_by(user_id=token_record.user_id, is_revoked=False).update(
            {"is_revoked": True}
        )
        db.commit()
        raise InvalidTokenServiceError("Revoked token reuse detected. All sessions invalidated.")

    # Expiry Check
    expires_at = token_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if expires_at < now:
        token_record.is_revoked = True
        db.commit()
        raise InvalidTokenServiceError("Refresh token has expired.")

    # User Status Check
    user = db.query(User).filter_by(id=token_record.user_id).first()
    if not user or not user.is_active:
        raise InvalidTokenServiceError("User account not found or inactive.")

    # Issue new token pair
    access_token = create_access_token(subject=user.id, role=user.role)
    new_raw_refresh, new_token_hash, new_expires_at = create_refresh_token(subject=user.id)

    new_record = RefreshToken(
        id=uuid.uuid4(),
        token_hash=new_token_hash,
        user_id=user.id,
        expires_at=new_expires_at,
        is_revoked=False,
    )
    db.add(new_record)
    db.flush()

    # Invalidate old refresh token and link replacement
    token_record.is_revoked = True
    token_record.replaced_by_token_id = new_record.id
    db.commit()

    return TokenPairResult(
        access_token=access_token,
        raw_refresh_token=new_raw_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def revoke_refresh_token(db: Session, raw_refresh_token: str) -> None:
    """Revoke a refresh token on logout."""
    token_hash = hash_token(raw_refresh_token)
    token_record = db.query(RefreshToken).filter_by(token_hash=token_hash).first()
    if token_record:
        token_record.is_revoked = True
        db.commit()
