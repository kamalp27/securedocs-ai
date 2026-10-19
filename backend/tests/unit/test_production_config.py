"""Unit tests for configuration security and production environment validation."""

import pytest
from app.core.config import Settings


def test_development_defaults_are_safe_and_permissive():
    """Verify development mode allows default development secret with DEBUG=False default."""
    config = Settings(ENVIRONMENT="development")
    assert config.ENVIRONMENT == "development"
    assert config.DEBUG is False
    assert config.SECRET_KEY == "change-me-to-a-secure-random-secret-key-min-32-chars"
    assert config.RATE_LIMIT_ENABLED is True
    assert config.TRUST_PROXY_HEADERS is False


def test_production_rejects_default_dummy_secret_key():
    """Verify production fails to boot if the known dummy SECRET_KEY is used."""
    with pytest.raises(ValueError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="change-me-to-a-secure-random-secret-key-min-32-chars",
        )
    assert "Default SECRET_KEY is not permitted in production" in str(exc_info.value)


def test_staging_rejects_default_dummy_secret_key():
    """Verify staging environment also fails to boot if the dummy SECRET_KEY is used."""
    with pytest.raises(ValueError) as exc_info:
        Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="change-me-to-a-secure-random-secret-key-min-32-chars",
        )
    assert "Default SECRET_KEY is not permitted in staging" in str(exc_info.value)


def test_production_rejects_short_secret_key():
    """Verify production fails closed if SECRET_KEY has fewer than 32 characters."""
    with pytest.raises(ValueError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="short-secret-key-16b",
        )
    assert "must be at least 32 characters" in str(exc_info.value)


def test_production_accepts_valid_strong_secret_key():
    """Verify production initializes cleanly with a sufficiently strong secret key."""
    strong_key = "a" * 32
    config = Settings(
        ENVIRONMENT="production",
        SECRET_KEY=strong_key,
    )
    assert config.ENVIRONMENT == "production"
    assert config.SECRET_KEY == strong_key
    assert config.DEBUG is False
