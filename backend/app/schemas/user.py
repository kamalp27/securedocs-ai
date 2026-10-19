"""Pydantic v2 schemas for User entities."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """Base user attributes shared across schemas."""
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=255)


class UserRegister(UserBase):
    """Registration schema with strict password complexity rules."""
    password: str = Field(..., min_length=8, max_length=128, description="User password")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if v.strip() == "":
            raise ValueError("Password cannot be empty or solely whitespace.")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if len(v) > 128:
            raise ValueError("Password cannot exceed 128 characters.")
        return v


class UserLogin(BaseModel):
    """Login credentials schema."""
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class UserRead(UserBase):
    """Public user profile schema with safe fields (never exposes password or hash)."""
    id: uuid.UUID
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
