"""Governance API endpoints for permission and audit trail management."""
from __future__ import annotations

import json
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_correlation_id, get_current_membership
from app.core.exceptions import PermissionDenied
from app.db.models.audit import AuditEvent
from app.db.models.family import FamilyMembership, FamilyRole, PermissionGrant
from app.db.session import get_db
from app.schemas.governance import (
    AuditEventResponse,
    PermissionGrantCreate,
    PermissionGrantResponse,
    PermissionGrantUpdate,
)
from app.services.governance_service import GovernanceService

router = APIRouter()
_gov_service = GovernanceService()


def _to_grant_response(g: PermissionGrant) -> PermissionGrantResponse:
    constraints = {}
    if g.constraints_json:
        try:
            constraints = json.loads(g.constraints_json)
        except Exception:
            pass
    effect_str = g.effect.value if hasattr(g.effect, "value") else str(g.effect)
    return PermissionGrantResponse(
        id=g.id,
        family_id=g.family_id,
        subject_membership_id=g.subject_membership_id,
        resource=g.resource,
        action=g.action,
        effect=effect_str,
        approval_required=g.approval_required,
        constraints_json=constraints,
        is_active=g.is_active,
        created_at=g.created_at.isoformat(),
        updated_at=g.updated_at.isoformat(),
    )


@router.get("/members/{membership_id}/permissions", response_model=List[PermissionGrantResponse])
async def get_member_permissions(
    membership_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all permission grants for a member (FGP authorized)."""
    grants = await _gov_service.get_member_permissions(
        db=db,
        membership_id=membership_id,
        requesting_membership_id=membership.id,
        family_id=membership.family_id,
    )
    return [_to_grant_response(g) for g in grants]


@router.get("/permissions", response_model=List[PermissionGrantResponse])
async def list_permissions(
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """List all grants in the family (ADMIN only, FGP enforced)."""
    if membership.family_role != FamilyRole.ADMIN:
        raise PermissionDenied("Only administrators can list all family permissions")

    stmt = select(PermissionGrant).where(
        PermissionGrant.family_id == membership.family_id,
        PermissionGrant.is_active == True,
    )
    result = await db.execute(stmt)
    grants = result.scalars().all()
    return [_to_grant_response(g) for g in grants]


@router.post("/permissions", response_model=PermissionGrantResponse)
async def create_permission(
    req: PermissionGrantCreate,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Create a new permission grant (ADMIN only, FGP enforced)."""
    grant = await _gov_service.create_permission(
        db=db,
        family_id=membership.family_id,
        admin_membership_id=membership.id,
        data=req,
        correlation_id=correlation_id,
    )
    return _to_grant_response(grant)


@router.patch("/permissions/{permission_id}", response_model=PermissionGrantResponse)
async def update_permission(
    permission_id: str,
    req: PermissionGrantUpdate,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Update a permission grant (ADMIN only, FGP enforced)."""
    grant = await _gov_service.update_permission(
        db=db,
        family_id=membership.family_id,
        admin_membership_id=membership.id,
        permission_id=permission_id,
        data=req,
        correlation_id=correlation_id,
    )
    return _to_grant_response(grant)


@router.delete("/permissions/{permission_id}")
async def delete_permission(
    permission_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Soft-delete/revoke a permission grant, maintaining audit log."""
    await _gov_service.delete_permission(
        db=db,
        family_id=membership.family_id,
        admin_membership_id=membership.id,
        permission_id=permission_id,
        correlation_id=correlation_id,
    )
    return {"status": "ok", "message": "Permission revoked"}


@router.get("/audit", response_model=List[AuditEventResponse])
async def get_audit_trail(
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve immutable audit event trail (ADMIN only)."""
    if membership.family_role != FamilyRole.ADMIN:
        raise PermissionDenied("Only administrators can view the audit trail")

    stmt = (
        select(AuditEvent)
        .where(AuditEvent.family_id == membership.family_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    res = []
    for e in events:
        meta = {}
        if e.metadata_json:
            try:
                meta = json.loads(e.metadata_json)
            except Exception:
                pass
        res.append(
            AuditEventResponse(
                id=e.id,
                family_id=e.family_id,
                actor_type=e.actor_type,
                actor_id=e.actor_id,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                decision=e.decision,
                reason_code=e.reason_code,
                correlation_id=e.correlation_id,
                metadata_json=meta,
                created_at=e.created_at.isoformat(),
            )
        )
    return res
