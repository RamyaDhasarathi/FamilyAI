"""Approval request Pydantic schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ApprovalRequestResponse(BaseModel):
    """Serialised approval request record."""

    id: str
    family_id: str
    purchase_task_id: str
    requested_by_membership_id: Optional[str]
    approver_membership_id: Optional[str]
    approval_type: str
    status: str
    request_payload_json: dict
    decision_reason: Optional[str]
    created_at: str
    decided_at: Optional[str]
    expires_at: Optional[str]


class ApprovalDecisionRequest(BaseModel):
    """Optional payload when approving or denying a request."""

    reason: Optional[str] = None
