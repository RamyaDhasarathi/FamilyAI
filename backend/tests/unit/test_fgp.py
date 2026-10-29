"""Unit tests for the Family Governance Platform (FGP) policy engine."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.family import (
    Family,
    FamilyMembership,
    FamilyRole,
    MembershipStatus,
    PermissionEffect,
    PermissionGrant,
)
from app.db.models.user import User
from app.policies.defaults import create_default_grants, create_member_default_grants
from app.policies.engine import PolicyEngine
from app.policies.rules import RA, validate_constraints

pytestmark = pytest.mark.asyncio
_engine = PolicyEngine()


async def _create_test_member(
    db: AsyncSession,
    role: FamilyRole,
    family_id: str | None = None,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> tuple[User, Family, FamilyMembership]:
    family_id = family_id or str(uuid.uuid4())
    family = await db.get(Family, family_id)
    if not family:
        family = Family(id=family_id, name="Test Family")
        db.add(family)

    user = User(
        id=str(uuid.uuid4()),
        email=f"user_{uuid.uuid4().hex[:6]}@test.local",
        display_name="Test User",
        password_hash="fakehash",
        is_active=True,
    )
    db.add(user)

    membership = FamilyMembership(
        id=str(uuid.uuid4()),
        family_id=family.id,
        user_id=user.id,
        family_role=role,
        membership_status=status,
    )
    db.add(membership)
    await db.flush()
    return user, family, membership


async def test_scenario_1_admin_can_update_permissions(db_session: AsyncSession):
    """1. Administrator can update permissions when authorized (implicit admin grant)."""
    _, family, admin_mem = await _create_test_member(db_session, FamilyRole.ADMIN)

    decision = await _engine.evaluate(
        db=db_session,
        principal_membership_id=admin_mem.id,
        family_id=family.id,
        resource=RA.FAMILY_PERMISSIONS_UPDATE[0],
        action=RA.FAMILY_PERMISSIONS_UPDATE[1],
    )
    assert decision.effect == "ALLOW"
    assert decision.reason_code == "ADMIN_IMPLICIT_GRANT"


async def test_scenario_2_adult_cannot_update_permissions_without_grant(db_session: AsyncSession):
    """2. An adult member cannot update permissions without an explicit grant."""
    _, family, adult_mem = await _create_test_member(db_session, FamilyRole.ADULT_MEMBER)

    decision = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource=RA.FAMILY_PERMISSIONS_UPDATE[0],
        action=RA.FAMILY_PERMISSIONS_UPDATE[1],
    )
    assert decision.effect == "DENY"
    assert decision.reason_code == "NO_GRANT"


async def test_scenario_3_child_cannot_update_permissions(db_session: AsyncSession):
    """3. A child member cannot update permissions."""
    _, family, child_mem = await _create_test_member(db_session, FamilyRole.CHILD_MEMBER)

    decision = await _engine.evaluate(
        db=db_session,
        principal_membership_id=child_mem.id,
        family_id=family.id,
        resource=RA.FAMILY_PERMISSIONS_UPDATE[0],
        action=RA.FAMILY_PERMISSIONS_UPDATE[1],
    )
    assert decision.effect == "DENY"
    assert decision.reason_code == "NO_GRANT"


async def test_scenario_4_missing_permissions_result_in_denial(db_session: AsyncSession):
    """4. Missing permissions result in default denial."""
    _, family, adult_mem = await _create_test_member(db_session, FamilyRole.ADULT_MEMBER)

    decision = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource="nonexistent.resource",
        action="execute",
    )
    assert decision.effect == "DENY"
    assert decision.reason_code == "NO_GRANT"


async def test_scenario_5_explicit_deny_rules_are_enforced(db_session: AsyncSession):
    """5. Explicit DENY grant overrides an ALLOW grant (deny wins)."""
    _, family, adult_mem = await _create_test_member(db_session, FamilyRole.ADULT_MEMBER)

    # Add ALLOW grant
    allow_grant = PermissionGrant(
        id=str(uuid.uuid4()),
        family_id=family.id,
        subject_membership_id=adult_mem.id,
        resource="purchase.task",
        action="create",
        effect=PermissionEffect.ALLOW,
        approval_required=False,
        created_by_membership_id=adult_mem.id,
    )
    # Add DENY grant
    deny_grant = PermissionGrant(
        id=str(uuid.uuid4()),
        family_id=family.id,
        subject_membership_id=adult_mem.id,
        resource="purchase.task",
        action="create",
        effect=PermissionEffect.DENY,
        approval_required=False,
        created_by_membership_id=adult_mem.id,
    )
    db_session.add_all([allow_grant, deny_grant])
    await db_session.flush()

    decision = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource="purchase.task",
        action="create",
    )
    assert decision.effect == "DENY"
    assert decision.reason_code == "EXPLICIT_DENY"


async def test_scenario_6_search_does_not_imply_execute(db_session: AsyncSession):
    """6. Grant for search does NOT automatically grant execute authority."""
    _, family, adult_mem = await _create_test_member(db_session, FamilyRole.ADULT_MEMBER)

    # Grant search only
    grant = PermissionGrant(
        id=str(uuid.uuid4()),
        family_id=family.id,
        subject_membership_id=adult_mem.id,
        resource=RA.PURCHASE_CATALOGUE_SEARCH[0],
        action=RA.PURCHASE_CATALOGUE_SEARCH[1],
        effect=PermissionEffect.ALLOW,
        created_by_membership_id=adult_mem.id,
    )
    db_session.add(grant)
    await db_session.flush()

    search_dec = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource=RA.PURCHASE_CATALOGUE_SEARCH[0],
        action=RA.PURCHASE_CATALOGUE_SEARCH[1],
    )
    assert search_dec.effect == "ALLOW"

    exec_dec = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource=RA.PURCHASE_EXECUTION_EXECUTE[0],
        action=RA.PURCHASE_EXECUTION_EXECUTE[1],
    )
    assert exec_dec.effect == "DENY"


async def test_scenario_7_read_does_not_imply_write(db_session: AsyncSession):
    """7. Read permission does not imply write/update permission."""
    _, family, adult_mem = await _create_test_member(db_session, FamilyRole.ADULT_MEMBER)

    grant = PermissionGrant(
        id=str(uuid.uuid4()),
        family_id=family.id,
        subject_membership_id=adult_mem.id,
        resource="purchase.task",
        action="read",
        effect=PermissionEffect.ALLOW,
        created_by_membership_id=adult_mem.id,
    )
    db_session.add(grant)
    await db_session.flush()

    read_dec = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource="purchase.task",
        action="read",
    )
    assert read_dec.effect == "ALLOW"

    update_dec = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource="purchase.task",
        action="update",
    )
    assert update_dec.effect == "DENY"


async def test_scenario_8_approval_required_returns_ask(db_session: AsyncSession):
    """8. An approval-required policy returns effect 'ASK'."""
    _, family, adult_mem = await _create_test_member(db_session, FamilyRole.ADULT_MEMBER)

    grant = PermissionGrant(
        id=str(uuid.uuid4()),
        family_id=family.id,
        subject_membership_id=adult_mem.id,
        resource="purchase.execution",
        action="execute",
        effect=PermissionEffect.ALLOW,
        approval_required=True,
        created_by_membership_id=adult_mem.id,
    )
    db_session.add(grant)
    await db_session.flush()

    decision = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource="purchase.execution",
        action="execute",
    )
    assert decision.effect == "ASK"
    assert decision.approval_required is True
    assert decision.reason_code == "APPROVAL_REQUIRED"


async def test_scenario_9_expired_approvals_rejected(db_session: AsyncSession):
    """9. Expired approvals are rejected."""
    from app.db.models.approval import ApprovalRequest, ApprovalStatus
    from app.services.approval_service import ApprovalService
    from app.core.exceptions import ApprovalExpired

    _, family, admin_mem = await _create_test_member(db_session, FamilyRole.ADMIN)

    appr = ApprovalRequest(
        id=str(uuid.uuid4()),
        family_id=family.id,
        purchase_task_id=str(uuid.uuid4()),
        requested_by_membership_id=admin_mem.id,
        approval_type="PURCHASE",
        status=ApprovalStatus.PENDING,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(appr)
    await db_session.flush()

    service = ApprovalService()
    with pytest.raises(ApprovalExpired):
        await service.approve(
            db=db_session,
            approval_id=appr.id,
            approver_membership_id=admin_mem.id,
            family_id=family.id,
        )


async def test_scenario_10_revoked_memberships_rejected(db_session: AsyncSession):
    """10. Revoked memberships are denied all access."""
    _, family, revoked_mem = await _create_test_member(
        db_session, FamilyRole.ADULT_MEMBER, status=MembershipStatus.REVOKED
    )

    decision = await _engine.evaluate(
        db=db_session,
        principal_membership_id=revoked_mem.id,
        family_id=family.id,
        resource="agent.purchase",
        action="use",
    )
    assert decision.effect == "DENY"
    assert decision.reason_code == "MEMBERSHIP_INVALID"


async def test_scenario_11_policy_changes_respected_before_execution(db_session: AsyncSession):
    """11. Revoking a grant immediately denies execution even if previously allowed."""
    _, family, adult_mem = await _create_test_member(db_session, FamilyRole.ADULT_MEMBER)

    grant = PermissionGrant(
        id=str(uuid.uuid4()),
        family_id=family.id,
        subject_membership_id=adult_mem.id,
        resource="mobile_use.instruction",
        action="execute",
        effect=PermissionEffect.ALLOW,
        approval_required=False,
        created_by_membership_id=adult_mem.id,
    )
    db_session.add(grant)
    await db_session.flush()

    dec1 = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource="mobile_use.instruction",
        action="execute",
    )
    assert dec1.effect == "ALLOW"

    # Admin deactivates grant
    grant.is_active = False
    await db_session.flush()

    dec2 = await _engine.evaluate(
        db=db_session,
        principal_membership_id=adult_mem.id,
        family_id=family.id,
        resource="mobile_use.instruction",
        action="execute",
    )
    assert dec2.effect == "DENY"


async def test_scenario_12_unknown_constraints_rejected():
    """12. Unknown security-sensitive constraints for execution actions return False."""
    valid_constraints = {
        "max_spend": 1500,
        "currency": "INR",
        "requires_user_confirmation": True,
    }
    assert validate_constraints(valid_constraints, "execute") is True

    unknown_constraints = {
        "bypass_security_check": True,
        "arbitrary_dangerous_flag": 123,
    }
    assert validate_constraints(unknown_constraints, "execute") is False
