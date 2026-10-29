"""Security and cross-family / cross-member isolation tests."""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.models.family import Family, FamilyMembership, FamilyRole, MembershipStatus
from app.db.models.purchase import PurchaseTask, PurchaseTaskStatus
from app.db.models.user import User

pytestmark = pytest.mark.asyncio


async def test_invalid_login_credentials(client: AsyncClient, bootstrapped_admin):
    """Invalid credentials should return 401."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@family.local", "password": "WrongPassword!"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_REQUIRED"


async def test_missing_token_returns_401(client: AsyncClient):
    """Calling protected endpoint without auth returns 401."""
    resp = await client.get("/api/v1/families/current")
    assert resp.status_code == 401


async def test_inactive_user_rejected(client: AsyncClient, db_session: AsyncSession, bootstrapped_admin):
    """Inactive users are barred from logging in or using endpoints."""
    user = await db_session.get(User, bootstrapped_admin["user_id"])
    user.is_active = False
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@family.local", "password": "Password123!"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_INACTIVE"


async def test_cross_family_isolation(client: AsyncClient, db_session: AsyncSession, bootstrapped_admin):
    """A user in Family A cannot access or see tasks from Family B."""
    # Create Family B with user B
    fam_b = Family(id=str(uuid.uuid4()), name="Family B")
    user_b = User(
        id=str(uuid.uuid4()),
        email="userb@familyb.local",
        display_name="User B",
        password_hash="fake",
        is_active=True,
    )
    mem_b = FamilyMembership(
        id=str(uuid.uuid4()),
        family_id=fam_b.id,
        user_id=user_b.id,
        family_role=FamilyRole.ADULT_MEMBER,
        membership_status=MembershipStatus.ACTIVE,
    )
    # Task in Family B
    task_b = PurchaseTask(
        id=str(uuid.uuid4()),
        family_id=fam_b.id,
        requester_membership_id=mem_b.id,
        conversation_id="conv_b",
        original_request="Private task B",
        status=PurchaseTaskStatus.RECEIVED,
    )
    db_session.add_all([fam_b, user_b, mem_b, task_b])
    await db_session.commit()

    # Admin A tries to get task B
    headers_a = {"Authorization": f"Bearer {bootstrapped_admin['access_token']}"}
    resp = await client.get(f"/api/v1/purchases/{task_b.id}", headers=headers_a)
    assert resp.status_code == 404  # Isolated: not found in family A


async def test_unauthorized_permission_update_by_non_admin(client: AsyncClient, db_session: AsyncSession, bootstrapped_admin):
    """An adult member without admin rights cannot modify permissions."""
    # Add adult member
    add_resp = await client.post(
        "/api/v1/families/current/members",
        headers={"Authorization": f"Bearer {bootstrapped_admin['access_token']}"},
        json={
            "email": "adult@family.local",
            "password": "Password123!",
            "display_name": "Adult Member",
            "role": "ADULT_MEMBER",
        },
    )
    assert add_resp.status_code == 200

    # Login as adult
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "adult@family.local", "password": "Password123!"},
    )
    adult_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    # Attempt to create grant
    perm_resp = await client.post(
        "/api/v1/governance/permissions",
        headers=adult_headers,
        json={
            "subject_membership_id": login_resp.json()["membership_id"],
            "resource": "purchase.execution",
            "action": "execute",
            "effect": "ALLOW",
        },
    )
    assert perm_resp.status_code == 403
    assert perm_resp.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_unauthorized_approval_decision(client: AsyncClient, db_session: AsyncSession, bootstrapped_admin):
    """An ordinary adult member cannot approve requests."""
    # Add adult member
    add_resp = await client.post(
        "/api/v1/families/current/members",
        headers={"Authorization": f"Bearer {bootstrapped_admin['access_token']}"},
        json={
            "email": "adult2@family.local",
            "password": "Password123!",
            "display_name": "Adult 2",
            "role": "ADULT_MEMBER",
        },
    )
    assert add_resp.status_code == 200

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "adult2@family.local", "password": "Password123!"},
    )
    adult_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    # Attempt to list pending approvals
    list_resp = await client.get("/api/v1/approvals/pending", headers=adult_headers)
    assert list_resp.status_code == 403
    assert list_resp.json()["error"]["code"] == "PERMISSION_DENIED"
