"""Family and membership Pydantic schemas for the Family OS API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MemberCreate(BaseModel):
    """Payload to invite / create a new family member account."""

    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    display_name: str
    role: str  # ADMIN | ADULT_MEMBER | CHILD_MEMBER


class MemberResponse(BaseModel):
    """Public profile of a family member."""

    membership_id: str
    user_id: str
    email: str
    display_name: str
    family_role: str
    membership_status: str
    created_at: str


class FamilyResponse(BaseModel):
    """Summary of the family record."""

    family_id: str
    name: str
    created_at: str
    member_count: int
