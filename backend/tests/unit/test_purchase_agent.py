"""Unit tests for the Purchase Agent."""
from __future__ import annotations

import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.purchase_agent import PurchaseAgent
from app.db.models.family import (
    Family,
    FamilyMembership,
    FamilyRole,
    MembershipStatus,
    PermissionEffect,
    PermissionGrant,
)
from app.db.models.user import User
from app.policies.defaults import create_default_grants

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def active_admin_membership(db_session: AsyncSession):
    fam = Family(id=str(uuid.uuid4()), name="Agent Test Family")
    user = User(
        id=str(uuid.uuid4()),
        email="agent_test@family.local",
        display_name="Agent Tester",
        password_hash="pwd",
        is_active=True,
    )
    mem = FamilyMembership(
        id=str(uuid.uuid4()),
        family_id=fam.id,
        user_id=user.id,
        family_role=FamilyRole.ADMIN,
        membership_status=MembershipStatus.ACTIVE,
    )
    db_session.add_all([fam, user, mem])
    await db_session.flush()
    await create_default_grants(db_session, fam.id, mem.id)
    await db_session.commit()
    return mem


async def test_purchase_agent_find_mouse_flow(db_session: AsyncSession, active_admin_membership):
    """Test text request: 'Find me a wireless mouse under 1500'."""
    agent = PurchaseAgent()
    result = await agent.process_message(
        db=db_session,
        conversation_id=None,
        user_message="Find me a wireless mouse under ₹1,500",
        task_id=None,
        membership=active_admin_membership,
    )

    assert result["agent_type"] == "PURCHASE"
    assert result["task_id"] is not None
    assert result["task_status"] == "RECOMMENDATION_READY"
    assert result["is_development_data"] is True
    assert len(result["candidates"]) > 0

    # Verify candidate properties
    first = result["candidates"][0]
    assert first["price_amount"] <= 1500
    assert first["source_type"] == "DEVELOPMENT_CATALOGUE"
    assert "score" in first
    assert "rank" in first


async def test_purchase_agent_brand_preference_ranking(db_session: AsyncSession, active_admin_membership):
    """Logitech preference should boost Logitech candidates to the top rank."""
    agent = PurchaseAgent()
    result = await agent.process_message(
        db=db_session,
        conversation_id=None,
        user_message="Find a Logitech wireless mouse",
        task_id=None,
        membership=active_admin_membership,
    )

    assert len(result["candidates"]) > 0
    top_cand = result["candidates"][0]
    assert top_cand["brand"].lower() == "logitech"


async def test_purchase_agent_unmatched_category(db_session: AsyncSession, active_admin_membership):
    """When a product category has no matches, it returns a helpful message."""
    agent = PurchaseAgent()
    result = await agent.process_message(
        db=db_session,
        conversation_id=None,
        user_message="Find an exotic spaceship under 100",
        task_id=None,
        membership=active_admin_membership,
    )
    assert result["candidates"] == []
