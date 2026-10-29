"""Family and member management endpoints."""
from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_correlation_id, get_current_membership, get_current_user
from app.db.models.family import Family, FamilyMembership, MembershipStatus
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.family import FamilyResponse, MemberCreate, MemberResponse
from app.services.governance_service import GovernanceService

router = APIRouter()
_gov_service = GovernanceService()


@router.get("/current", response_model=FamilyResponse)
async def get_current_family(
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details of the authenticated member's family."""
    family = await db.get(Family, membership.family_id)
    count_res = await db.execute(
        select(func.count(FamilyMembership.id)).where(
            FamilyMembership.family_id == membership.family_id,
            FamilyMembership.membership_status == MembershipStatus.ACTIVE,
        )
    )
    count = count_res.scalar() or 1

    return FamilyResponse(
        family_id=family.id,
        name=family.name,
        created_at=family.created_at.isoformat(),
        member_count=count,
    )


@router.get("/current/members", response_model=List[MemberResponse])
async def list_family_members(
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """List all members of the family (FGP authorized)."""
    members = await _gov_service.get_family_members(
        db=db,
        family_id=membership.family_id,
        requesting_membership_id=membership.id,
    )
    res = []
    for m in members:
        user = await db.get(User, m.user_id)
        role_str = m.family_role.value if hasattr(m.family_role, "value") else str(m.family_role)
        status_str = m.membership_status.value if hasattr(m.membership_status, "value") else str(m.membership_status)
        res.append(
            MemberResponse(
                membership_id=m.id,
                user_id=m.user_id,
                email=user.email if user else "",
                display_name=user.display_name if user else "",
                family_role=role_str,
                membership_status=status_str,
                created_at=m.created_at.isoformat(),
            )
        )
    return res


@router.post("/current/members", response_model=MemberResponse)
async def add_family_member(
    req: MemberCreate,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Add a new member to the family (ADMIN only, FGP enforced)."""
    new_mem = await _gov_service.add_family_member(
        db=db,
        family_id=membership.family_id,
        admin_membership_id=membership.id,
        email=req.email,
        display_name=req.display_name,
        password=req.password,
        role=req.role,
        correlation_id=correlation_id,
    )
    user = await db.get(User, new_mem.user_id)
    role_str = new_mem.family_role.value if hasattr(new_mem.family_role, "value") else str(new_mem.family_role)
    status_str = new_mem.membership_status.value if hasattr(new_mem.membership_status, "value") else str(new_mem.membership_status)

    return MemberResponse(
        membership_id=new_mem.id,
        user_id=new_mem.user_id,
        email=user.email if user else req.email,
        display_name=user.display_name if user else req.display_name,
        family_role=role_str,
        membership_status=status_str,
        created_at=new_mem.created_at.isoformat(),
    )


@router.get("/current/members/{membership_id}", response_model=MemberResponse)
async def get_family_member(
    membership_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Get single member profile."""
    from app.core.exceptions import NotFoundError
    target_mem = await db.get(FamilyMembership, membership_id)
    if not target_mem or target_mem.family_id != membership.family_id:
        raise NotFoundError("FamilyMembership", membership_id)

    user = await db.get(User, target_mem.user_id)
    role_str = target_mem.family_role.value if hasattr(target_mem.family_role, "value") else str(target_mem.family_role)
    status_str = target_mem.membership_status.value if hasattr(target_mem.membership_status, "value") else str(target_mem.membership_status)

    return MemberResponse(
        membership_id=target_mem.id,
        user_id=target_mem.user_id,
        email=user.email if user else "",
        display_name=user.display_name if user else "",
        family_role=role_str,
        membership_status=status_str,
        created_at=target_mem.created_at.isoformat(),
    )
