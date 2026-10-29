"""Default permission grants applied during family bootstrap and member onboarding."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.family import PermissionEffect, PermissionGrant
from app.policies.rules import RA


# ── Baseline for ADULT_MEMBER role ────────────────────────────────────────────

def get_adult_member_default_grants() -> List[Tuple[str, str, bool]]:
    """Return the baseline grants to apply when an ADULT_MEMBER is onboarded.

    Each tuple is ``(resource, action, approval_required)``.  All grants have
    ``PermissionEffect.ALLOW`` and no constraints.

    Returns:
        List of ``(resource, action, approval_required)`` tuples.
    """
    return [
        (*RA.AGENT_PURCHASE_USE, False),
        (*RA.PURCHASE_TASK_CREATE, False),
        (*RA.PURCHASE_TASK_READ, False),
        (*RA.PURCHASE_CATALOGUE_SEARCH, False),
        (*RA.PURCHASE_PRODUCT_SELECT, False),
        (*RA.PURCHASE_EXECUTION_PREPARE, True),   # requires approval
        (*RA.PURCHASE_EXECUTION_SIMULATE, False),
        (*RA.VOICE_TRANSCRIPTION_USE, False),
        (*RA.VOICE_SPEECH_GENERATE, False),
    ]


# ── Bootstrap admin grants ────────────────────────────────────────────────────

async def create_default_grants(
    db: AsyncSession,
    family_id: str,
    admin_membership_id: str,
) -> None:
    """Persist the full set of default grants for the bootstrap admin member.

    Every :class:`~app.policies.rules.RA` resource/action combination is
    granted to the admin with ``PermissionEffect.ALLOW`` and
    ``approval_required=False``.  These grants are owned by the admin
    themselves (``created_by_membership_id == admin_membership_id``).

    Args:
        db: An active async SQLAlchemy session.  The caller is responsible for
            committing the transaction.
        family_id: UUID of the family these grants belong to.
        admin_membership_id: UUID of the admin's :class:`FamilyMembership`.
    """
    now = datetime.now(timezone.utc)
    all_ra = RA.all()

    for resource, action in all_ra:
        grant = PermissionGrant(
            id=str(uuid.uuid4()),
            family_id=family_id,
            subject_membership_id=admin_membership_id,
            resource=resource,
            action=action,
            effect=PermissionEffect.ALLOW,
            approval_required=False,
            constraints_json=json.dumps({}),
            created_by_membership_id=admin_membership_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(grant)


async def create_member_default_grants(
    db: AsyncSession,
    family_id: str,
    subject_membership_id: str,
    created_by_membership_id: str,
) -> None:
    """Persist the default ADULT_MEMBER grants for a newly created member.

    Args:
        db: An active async SQLAlchemy session.  The caller is responsible for
            committing the transaction.
        family_id: UUID of the family these grants belong to.
        subject_membership_id: UUID of the new member's :class:`FamilyMembership`.
        created_by_membership_id: UUID of the admin membership creating these grants.
    """
    now = datetime.now(timezone.utc)
    default_grants = get_adult_member_default_grants()

    for resource, action, approval_required in default_grants:
        grant = PermissionGrant(
            id=str(uuid.uuid4()),
            family_id=family_id,
            subject_membership_id=subject_membership_id,
            resource=resource,
            action=action,
            effect=PermissionEffect.ALLOW,
            approval_required=approval_required,
            constraints_json=json.dumps({}),
            created_by_membership_id=created_by_membership_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(grant)
