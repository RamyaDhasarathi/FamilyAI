"""Core policy evaluation engine for the Family Governance Platform (FGP).

IMPORTANT: This engine is purely deterministic. It NEVER consults an LLM or
any probabilistic system for authorization decisions. All decisions are based
solely on database-persisted PermissionGrant records and hard-coded role rules.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.family import (
    FamilyMembership,
    FamilyRole,
    MembershipStatus,
    PermissionEffect,
    PermissionGrant,
)
from app.db.models.user import User


# ── Output model ──────────────────────────────────────────────────────────────


class PolicyDecision(BaseModel):
    """Immutable result of a policy evaluation.

    ``effect`` is one of:
    - ``"ALLOW"``  – the action is permitted without further gating.
    - ``"DENY"``   – the action is explicitly prohibited.
    - ``"ASK"``    – a grant exists but ``approval_required=True``; the caller
                     must raise an approval request before proceeding.
    """

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    effect: Literal["ALLOW", "DENY", "ASK"]
    reason_code: str
    human_readable_reason: str
    approval_required: bool
    constraints: dict = Field(default_factory=dict)
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    policy_version: str = "1.0"


# ── Admin implicit grants ─────────────────────────────────────────────────────

# ADMIN role members receive implicit ALLOW for these management actions.
# This list intentionally excludes any access to other members' private data.
_ADMIN_IMPLICIT_GRANTS: frozenset[tuple[str, str]] = frozenset(
    {
        ("family.members", "read"),
        ("family.permissions", "read"),
        ("family.permissions", "update"),
        ("approval.request", "decide"),
    }
)


# ── Engine ────────────────────────────────────────────────────────────────────


class PolicyEngine:
    """Stateless policy evaluation engine.

    Instantiate once (e.g., as a module-level singleton) and call
    :meth:`evaluate` for every authorization check.  The engine holds no
    mutable state; all data is fetched fresh from the database on each call
    so that permission changes take effect immediately.
    """

    async def evaluate(
        self,
        db: AsyncSession,
        principal_membership_id: str,
        family_id: str,
        resource: str,
        action: str,
        purpose: str = "",
        context: Optional[dict] = None,
    ) -> PolicyDecision:
        """Evaluate whether *principal* may perform *action* on *resource*.

        Evaluation order:
        1. Validate that the membership exists, belongs to *family_id*, and is
           ``ACTIVE``.
        2. Validate that the underlying user account is active.
        3. Check explicit ``PermissionGrant`` records – DENY wins over ALLOW.
        4. Apply implicit ADMIN grants for approved management resources.
        5. Default-deny everything else.

        Args:
            db: An active async SQLAlchemy session.
            principal_membership_id: The UUID of the :class:`FamilyMembership`
                whose permissions are being evaluated.
            family_id: Expected family scope for the membership.
            resource: Resource identifier (e.g. ``"purchase.execution"``).
            action: Action identifier (e.g. ``"execute"``).
            purpose: Optional free-text purpose supplied by the caller
                (stored in audit records; not used for decisions).
            context: Optional extra context dict (not used for decisions).

        Returns:
            A :class:`PolicyDecision` describing the outcome.
        """
        # ── 1. Load and validate membership ──────────────────────────────────
        membership_result = await db.execute(
            select(FamilyMembership).where(
                and_(
                    FamilyMembership.id == principal_membership_id,
                    FamilyMembership.family_id == family_id,
                )
            )
        )
        membership: Optional[FamilyMembership] = membership_result.scalar_one_or_none()

        if membership is None or membership.membership_status != MembershipStatus.ACTIVE:
            return PolicyDecision(
                effect="DENY",
                reason_code="MEMBERSHIP_INVALID",
                human_readable_reason=(
                    "No active family membership found for the given principal in "
                    "this family."
                ),
                approval_required=False,
            )

        # ── 2. Validate user account ──────────────────────────────────────────
        user_result = await db.execute(
            select(User).where(User.id == membership.user_id)
        )
        user: Optional[User] = user_result.scalar_one_or_none()

        if user is None or not user.is_active:
            return PolicyDecision(
                effect="DENY",
                reason_code="ACCOUNT_INACTIVE",
                human_readable_reason="The user account associated with this membership is inactive.",
                approval_required=False,
            )

        # ── 3. Query explicit permission grants ───────────────────────────────
        grants_result = await db.execute(
            select(PermissionGrant).where(
                and_(
                    PermissionGrant.family_id == family_id,
                    PermissionGrant.subject_membership_id == principal_membership_id,
                    PermissionGrant.resource == resource,
                    PermissionGrant.action == action,
                    PermissionGrant.is_active.is_(True),
                )
            )
        )
        grants: list[PermissionGrant] = list(grants_result.scalars().all())

        # Sort: DENY grants evaluated first (deny wins)
        deny_grants = [g for g in grants if g.effect == PermissionEffect.DENY]
        allow_grants = [g for g in grants if g.effect == PermissionEffect.ALLOW]

        if deny_grants:
            return PolicyDecision(
                effect="DENY",
                reason_code="EXPLICIT_DENY",
                human_readable_reason=(
                    f"An explicit DENY grant exists for {resource}/{action}."
                ),
                approval_required=False,
            )

        if allow_grants:
            # Use the first (most specific) allow grant.
            grant = allow_grants[0]
            try:
                constraints = json.loads(grant.constraints_json or "{}")
            except (json.JSONDecodeError, TypeError):
                constraints = {}

            if grant.approval_required:
                return PolicyDecision(
                    effect="ASK",
                    reason_code="APPROVAL_REQUIRED",
                    human_readable_reason=(
                        f"Permission to {action} on {resource} requires approval."
                    ),
                    approval_required=True,
                    constraints=constraints,
                )

            return PolicyDecision(
                effect="ALLOW",
                reason_code="EXPLICIT_ALLOW",
                human_readable_reason=(
                    f"Explicit grant allows {action} on {resource}."
                ),
                approval_required=False,
                constraints=constraints,
            )

        # ── 4. Implicit ADMIN grants ──────────────────────────────────────────
        if membership.family_role == FamilyRole.ADMIN:
            if (resource, action) in _ADMIN_IMPLICIT_GRANTS:
                return PolicyDecision(
                    effect="ALLOW",
                    reason_code="ADMIN_IMPLICIT_GRANT",
                    human_readable_reason=(
                        f"ADMIN role implicitly allows {action} on {resource}."
                    ),
                    approval_required=False,
                )

        # ── 5. Default deny ───────────────────────────────────────────────────
        return PolicyDecision(
            effect="DENY",
            reason_code="NO_GRANT",
            human_readable_reason=(
                f"No permission grant exists for {resource}/{action}. "
                "Default policy is DENY."
            ),
            approval_required=False,
        )
