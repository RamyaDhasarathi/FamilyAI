"""Family Governance Platform (FGP) service.

Manages permission grants and family membership through a policy-gated API.
All mutating operations require the caller to be an ADMIN of the family and
are validated through :class:`~app.policies.engine.PolicyEngine` before being
applied.  Every write is accompanied by an audit event.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDenied, ValidationError
from app.core.security import hash_password
from app.db.models.family import (
    FamilyMembership,
    FamilyRole,
    MembershipStatus,
    PermissionEffect,
    PermissionGrant,
)
from app.db.models.user import User
from app.policies.defaults import create_member_default_grants
from app.policies.engine import PolicyEngine
from app.policies.rules import RA
from app.schemas.governance import PermissionGrantCreate, PermissionGrantUpdate
from app.services.audit_service import AuditService

_engine = PolicyEngine()
_auditor = AuditService()


class GovernanceService:
    """High-level service for FGP permission and membership management.

    All public methods perform policy checks before executing any write.
    """

    # ── Permissions ───────────────────────────────────────────────────────────

    async def get_member_permissions(
        self,
        db: AsyncSession,
        membership_id: str,
        requesting_membership_id: str,
        family_id: str,
    ) -> List[PermissionGrant]:
        """Return all active grants for *membership_id*.

        The caller (*requesting_membership_id*) must have
        ``family.permissions/read`` or be requesting their own grants.

        Args:
            db: Active async SQLAlchemy session.
            membership_id: UUID of the membership whose grants are requested.
            requesting_membership_id: UUID of the membership making the request.
            family_id: Family scope.

        Returns:
            List of :class:`~app.db.models.family.PermissionGrant` rows.

        Raises:
            :class:`~app.core.exceptions.PermissionDenied`: If the caller lacks
                the required ``family.permissions/read`` grant and is not
                querying their own membership.
        """
        # Allow self-read without a policy check
        if requesting_membership_id != membership_id:
            resource, action = RA.FAMILY_PERMISSIONS_READ
            decision = await _engine.evaluate(
                db,
                principal_membership_id=requesting_membership_id,
                family_id=family_id,
                resource=resource,
                action=action,
            )
            if decision.effect != "ALLOW":
                raise PermissionDenied(
                    f"You do not have permission to read other members' grants "
                    f"({decision.reason_code})."
                )

        result = await db.execute(
            select(PermissionGrant).where(
                and_(
                    PermissionGrant.family_id == family_id,
                    PermissionGrant.subject_membership_id == membership_id,
                    PermissionGrant.is_active.is_(True),
                )
            )
        )
        return list(result.scalars().all())

    async def create_permission(
        self,
        db: AsyncSession,
        family_id: str,
        admin_membership_id: str,
        data: PermissionGrantCreate,
        correlation_id: str = "create_perm",
    ) -> PermissionGrant:
        """Create a new permission grant.

        Args:
            db: Active async SQLAlchemy session.
            family_id: Family scope.
            admin_membership_id: UUID of the ADMIN membership authorising the change.
            data: Grant creation payload.
            correlation_id: Correlation ID for audit.

        Returns:
            The newly created :class:`~app.db.models.family.PermissionGrant`.

        Raises:
            :class:`~app.core.exceptions.PermissionDenied`: If the caller is
                not an ADMIN or lacks the ``family.permissions/update`` grant.
        """
        await self._assert_can_update_permissions(db, admin_membership_id, family_id)

        now = datetime.now(timezone.utc)
        constraints = getattr(data, "constraints_json", None) or getattr(data, "constraints", {})
        grant = PermissionGrant(
            id=str(uuid.uuid4()),
            family_id=family_id,
            subject_membership_id=data.subject_membership_id,
            resource=data.resource,
            action=data.action,
            effect=PermissionEffect(data.effect),
            approval_required=data.approval_required,
            constraints_json=json.dumps(constraints),
            created_by_membership_id=admin_membership_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(grant)
        await db.flush()

        await _auditor.log(
            db,
            family_id=family_id,
            actor_type="USER",
            actor_id=admin_membership_id,
            action="permission.create",
            resource_type="permission_grant",
            resource_id=grant.id,
            decision="ALLOW",
            reason_code="ADMIN_ACTION",
            correlation_id=correlation_id,
            metadata={
                "subject_membership_id": data.subject_membership_id,
                "resource": data.resource,
                "action": data.action,
                "effect": data.effect,
            },
        )
        return grant

    async def update_permission(
        self,
        db: AsyncSession,
        family_id: str,
        admin_membership_id: str,
        permission_id: str,
        data: PermissionGrantUpdate,
        correlation_id: str = "update_perm",
    ) -> PermissionGrant:
        """Update an existing permission grant."""
        await self._assert_can_update_permissions(db, admin_membership_id, family_id)

        grant = await self._get_grant_or_404(db, permission_id, family_id)

        if data.effect is not None:
            grant.effect = PermissionEffect(data.effect)
        if data.approval_required is not None:
            grant.approval_required = data.approval_required
        constraints = getattr(data, "constraints_json", None) or getattr(data, "constraints", None)
        if constraints is not None:
            grant.constraints_json = json.dumps(constraints)
        if data.is_active is not None:
            grant.is_active = data.is_active
        grant.updated_at = datetime.now(timezone.utc)

        await db.flush()

        await _auditor.log(
            db,
            family_id=family_id,
            actor_type="USER",
            actor_id=admin_membership_id,
            action="permission.update",
            resource_type="permission_grant",
            resource_id=permission_id,
            decision="ALLOW",
            reason_code="ADMIN_ACTION",
            correlation_id=correlation_id,
            metadata={"changes": data.model_dump(exclude_none=True)},
        )
        return grant

    async def delete_permission(
        self,
        db: AsyncSession,
        family_id: str,
        admin_membership_id: str,
        permission_id: str,
        correlation_id: str = "delete_perm",
    ) -> None:
        """Soft-delete a permission grant by setting ``is_active=False``."""
        await self._assert_can_update_permissions(db, admin_membership_id, family_id)

        grant = await self._get_grant_or_404(db, permission_id, family_id)
        grant.is_active = False
        grant.updated_at = datetime.now(timezone.utc)
        await db.flush()

        await _auditor.log(
            db,
            family_id=family_id,
            actor_type="USER",
            actor_id=admin_membership_id,
            action="permission.delete",
            resource_type="permission_grant",
            resource_id=permission_id,
            decision="ALLOW",
            reason_code="ADMIN_ACTION",
            correlation_id=correlation_id,
        )

    # ── Members ───────────────────────────────────────────────────────────────

    async def get_family_members(
        self,
        db: AsyncSession,
        family_id: str,
        requesting_membership_id: str,
    ) -> List[FamilyMembership]:
        """Return all ACTIVE memberships for *family_id*.

        Args:
            db: Active async SQLAlchemy session.
            family_id: Family scope.
            requesting_membership_id: UUID of the membership making the request.

        Returns:
            List of :class:`~app.db.models.family.FamilyMembership` rows.

        Raises:
            :class:`~app.core.exceptions.PermissionDenied`: If the caller lacks
                the ``family.members/read`` grant.
        """
        resource, action = RA.FAMILY_MEMBERS_READ
        decision = await _engine.evaluate(
            db,
            principal_membership_id=requesting_membership_id,
            family_id=family_id,
            resource=resource,
            action=action,
        )
        if decision.effect != "ALLOW":
            raise PermissionDenied(
                f"You do not have permission to list family members "
                f"({decision.reason_code})."
            )

        result = await db.execute(
            select(FamilyMembership).where(
                and_(
                    FamilyMembership.family_id == family_id,
                    FamilyMembership.membership_status == MembershipStatus.ACTIVE,
                )
            )
        )
        return list(result.scalars().all())

    async def add_family_member(
        self,
        db: AsyncSession,
        family_id: str,
        admin_membership_id: str,
        email: str,
        display_name: str,
        password: str,
        role: FamilyRole | str,
        correlation_id: str = "member_add",
    ) -> FamilyMembership:
        """Create a new user (if not exists) and active family membership with default grants."""
        await self._assert_admin(db, admin_membership_id, family_id)

        # Parse role
        if isinstance(role, str):
            try:
                role_enum = FamilyRole(role)
            except ValueError:
                role_enum = FamilyRole.ADULT_MEMBER
        else:
            role_enum = role

        # Check existing user
        user_res = await db.execute(select(User).where(User.email == email))
        user = user_res.scalar_one_or_none()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                display_name=display_name,
                password_hash=hash_password(password),
                is_active=True,
            )
            db.add(user)
            await db.flush()

        # Check existing active membership in this family
        mem_res = await db.execute(
            select(FamilyMembership).where(
                and_(
                    FamilyMembership.family_id == family_id,
                    FamilyMembership.user_id == user.id,
                    FamilyMembership.membership_status == MembershipStatus.ACTIVE,
                )
            )
        )
        if mem_res.scalar_one_or_none() is not None:
            raise ValidationError(f"User '{email}' is already an active member of this family")

        now = datetime.now(timezone.utc)
        membership = FamilyMembership(
            id=str(uuid.uuid4()),
            family_id=family_id,
            user_id=user.id,
            family_role=role_enum,
            membership_status=MembershipStatus.ACTIVE,
            created_at=now,
        )
        db.add(membership)
        await db.flush()

        if role_enum == FamilyRole.ADULT_MEMBER:
            await create_member_default_grants(
                db,
                family_id=family_id,
                subject_membership_id=membership.id,
                created_by_membership_id=admin_membership_id,
            )

        await _auditor.log(
            db,
            family_id=family_id,
            actor_type="USER",
            actor_id=admin_membership_id,
            action="member.add",
            resource_type="family_membership",
            resource_id=membership.id,
            decision="ALLOW",
            reason_code="ADMIN_ACTION",
            correlation_id=correlation_id,
            metadata={
                "email": email,
                "display_name": display_name,
                "role": role_enum.value,
            },
        )
        return membership

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _assert_can_update_permissions(
        self,
        db: AsyncSession,
        admin_membership_id: str,
        family_id: str,
    ) -> None:
        """Assert the caller has ``family.permissions/update`` access.

        Raises:
            :class:`~app.core.exceptions.PermissionDenied`: On failure.
        """
        resource, action = RA.FAMILY_PERMISSIONS_UPDATE
        decision = await _engine.evaluate(
            db,
            principal_membership_id=admin_membership_id,
            family_id=family_id,
            resource=resource,
            action=action,
        )
        if decision.effect != "ALLOW":
            raise PermissionDenied(
                f"You do not have permission to manage family permissions "
                f"({decision.reason_code})."
            )

    async def _assert_admin(
        self,
        db: AsyncSession,
        membership_id: str,
        family_id: str,
    ) -> FamilyMembership:
        """Assert the membership has the ADMIN role.

        Returns:
            The :class:`~app.db.models.family.FamilyMembership` if valid.

        Raises:
            :class:`~app.core.exceptions.PermissionDenied`: If not an ADMIN.
        """
        result = await db.execute(
            select(FamilyMembership).where(
                and_(
                    FamilyMembership.id == membership_id,
                    FamilyMembership.family_id == family_id,
                    FamilyMembership.membership_status == MembershipStatus.ACTIVE,
                )
            )
        )
        membership: Optional[FamilyMembership] = result.scalar_one_or_none()
        if membership is None or membership.family_role != FamilyRole.ADMIN:
            raise PermissionDenied("Only ADMIN members can perform this action.")
        return membership

    async def _get_grant_or_404(
        self,
        db: AsyncSession,
        permission_id: str,
        family_id: str,
    ) -> PermissionGrant:
        """Load a grant by ID scoped to *family_id* or raise 404.

        Raises:
            :class:`~app.core.exceptions.NotFoundError`: If not found.
        """
        result = await db.execute(
            select(PermissionGrant).where(
                and_(
                    PermissionGrant.id == permission_id,
                    PermissionGrant.family_id == family_id,
                )
            )
        )
        grant: Optional[PermissionGrant] = result.scalar_one_or_none()
        if grant is None:
            raise NotFoundError("PermissionGrant", permission_id)
        return grant
