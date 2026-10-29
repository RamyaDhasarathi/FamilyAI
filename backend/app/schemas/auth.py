"""Authentication Pydantic schemas for the Family OS API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class BootstrapRequest(BaseModel):
    """Payload to bootstrap the very first admin account."""

    bootstrap_token: str
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    display_name: str
    family_name: str


class LoginRequest(BaseModel):
    """Credentials for a password-based login."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """Access + refresh token pair returned after successful auth."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    display_name: str
    family_id: str
    membership_id: str
    family_role: str


class RefreshRequest(BaseModel):
    """Payload to exchange a refresh token for a new access token."""

    refresh_token: str


class UserInfo(BaseModel):
    """Public profile of the currently authenticated user."""

    user_id: str
    email: str
    display_name: str
    is_active: bool
    family_id: str
    membership_id: str
    family_role: str
    family_name: str
