"""Pydantic v2 schemas for Authentication and Token responses."""

from typing import Optional
from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Token response returned upon successful authentication or rotation."""
    access_token: str = Field(..., description="Short-lived JWT access token")
    token_type: str = Field("bearer", description="Token type indicator")
    expires_in: int = Field(..., description="Access token expiry duration in seconds")
    csrf_token: Optional[str] = Field(None, description="Anti-CSRF token for cookie-authenticated requests")


class TokenRefreshRequest(BaseModel):
    """Optional request payload for refresh (token is primarily transmitted via HttpOnly cookie)."""
    refresh_token: Optional[str] = Field(None, description="Optional raw refresh token for non-browser clients")


class LogoutRequest(BaseModel):
    """Optional request payload for logout (token is primarily transmitted via HttpOnly cookie)."""
    refresh_token: Optional[str] = Field(None, description="Optional raw refresh token for non-browser clients")


class MessageResponse(BaseModel):
    """Standard generic operational response message."""
    message: str
