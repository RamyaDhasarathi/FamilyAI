"""Governance / permission-grant Pydantic schemas for the Family OS API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PermissionGrantCreate(BaseModel):
    """Payload to create a new permission grant for a family member."""

    subject_membership_id: str
    resource: str
    action: str
    effect: str  # ALLOW | DENY
    approval_required: bool = False
    constraints_json: dict = {}


class PermissionGrantUpdate(BaseModel):
    """Partial update payload for an existing permission grant."""

    effect: Optional[str] = None
    approval_required: Optional[bool] = None
    constraints_json: Optional[dict] = None
    is_active: Optional[bool] = None


class PermissionGrantResponse(BaseModel):
    """Serialised permission grant record."""

    id: str
    family_id: str
    subject_membership_id: str
    resource: str
    action: str
    effect: str
    approval_required: bool
    constraints_json: dict
    is_active: bool
    created_at: str
    updated_at: str


class AuditEventResponse(BaseModel):
    """Serialised audit-event record (read-only)."""

    id: str
    family_id: Optional[str]
    actor_type: str
    actor_id: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    decision: Optional[str]
    reason_code: Optional[str]
    correlation_id: str
    metadata_json: dict
    created_at: str
