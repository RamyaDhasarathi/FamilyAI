"""Approval workflow API endpoints."""
from __future__ import annotations

import json
from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_correlation_id, get_current_membership
from app.db.models.approval import ApprovalRequest
from app.db.models.family import FamilyMembership
from app.db.session import get_db
from app.schemas.approval import ApprovalDecisionRequest, ApprovalRequestResponse
from app.services.approval_service import ApprovalService

router = APIRouter()
_approval_service = ApprovalService()


def _to_approval_response(a: ApprovalRequest) -> ApprovalRequestResponse:
    payload = {}
    if a.request_payload_json:
        try:
            payload = json.loads(a.request_payload_json)
        except Exception:
            pass
    status_str = a.status.value if hasattr(a.status, "value") else str(a.status)
    return ApprovalRequestResponse(
        id=a.id,
        family_id=a.family_id,
        purchase_task_id=a.purchase_task_id,
        requested_by_membership_id=a.requested_by_membership_id,
        approver_membership_id=a.approver_membership_id,
        approval_type=a.approval_type,
        status=status_str,
        request_payload_json=payload,
        decision_reason=a.decision_reason,
        created_at=a.created_at.isoformat(),
        decided_at=a.decided_at.isoformat() if a.decided_at else None,
        expires_at=a.expires_at.isoformat() if a.expires_at else None,
    )


@router.get("/pending", response_model=List[ApprovalRequestResponse])
async def get_pending_approvals(
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all pending approval requests in the family."""
    approvals = await _approval_service.get_pending(
        db=db,
        membership_id=membership.id,
        family_id=membership.family_id,
    )
    return [_to_approval_response(a) for a in approvals]


@router.get("/{approval_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    approval_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a specific approval request."""
    approval = await _approval_service.get_approval(
        db=db,
        approval_id=approval_id,
        membership_id=membership.id,
        family_id=membership.family_id,
    )
    return _to_approval_response(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalRequestResponse)
async def approve_request(
    approval_id: str,
    req: Optional[ApprovalDecisionRequest] = None,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Approve a pending request (ADMIN or authorized approver only)."""
    reason = req.reason if req else None
    approval = await _approval_service.approve(
        db=db,
        approval_id=approval_id,
        approver_membership_id=membership.id,
        family_id=membership.family_id,
        reason=reason,
        correlation_id=correlation_id,
    )
    return _to_approval_response(approval)


@router.post("/{approval_id}/deny", response_model=ApprovalRequestResponse)
async def deny_request(
    approval_id: str,
    req: Optional[ApprovalDecisionRequest] = None,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Deny a pending request."""
    reason = req.reason if req else None
    approval = await _approval_service.deny(
        db=db,
        approval_id=approval_id,
        approver_membership_id=membership.id,
        family_id=membership.family_id,
        reason=reason,
        correlation_id=correlation_id,
    )
    return _to_approval_response(approval)


@router.post("/{approval_id}/cancel", response_model=ApprovalRequestResponse)
async def cancel_request(
    approval_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an approval request."""
    approval = await _approval_service.cancel(
        db=db,
        approval_id=approval_id,
        membership_id=membership.id,
        family_id=membership.family_id,
    )
    return _to_approval_response(approval)
