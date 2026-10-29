"""Unit tests for the Mobile Use Agent."""
from __future__ import annotations

import json
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from unittest.mock import AsyncMock
from app.agents.adb_bridge import ADBBridge
from app.agents.mobile_use_agent import MobileUseAgent
from app.core.exceptions import InvalidInstruction, NotFoundError
from app.db.models.family import (
    Family,
    FamilyMembership,
    FamilyRole,
    MembershipStatus,
    PermissionEffect,
    PermissionGrant,
)
from app.db.models.mobile_use import InstructionStatus, MobileUseInstruction
from app.db.models.purchase import ExecutionState, PurchaseTask, PurchaseTaskStatus
from app.db.models.user import User
from app.policies.defaults import create_default_grants

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def setup_family_and_admin(db_session: AsyncSession):
    fam = Family(id=str(uuid.uuid4()), name="Mobile Use Family")
    user = User(
        id=str(uuid.uuid4()),
        email="mobile_tester@family.local",
        display_name="Mobile Tester",
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
    task = PurchaseTask(
        id=str(uuid.uuid4()),
        family_id=fam.id,
        requester_membership_id=mem.id,
        conversation_id="conv_1",
        original_request="Test task",
        status=PurchaseTaskStatus.OPTION_SELECTED,
    )
    db_session.add_all([fam, user, mem, task])
    await db_session.flush()
    await create_default_grants(db_session, fam.id, mem.id)
    await db_session.commit()
    return fam, mem, task


async def test_simulate_execution_success(db_session: AsyncSession, setup_family_and_admin):
    """Execution simulation runs and clearly returns the disclaimer."""
    fam, mem, task = setup_family_and_admin

    instruction = MobileUseInstruction(
        id=str(uuid.uuid4()),
        family_id=fam.id,
        purchase_task_id=task.id,
        created_by_agent="PurchaseAgent",
        action_type="SIMULATE_EXECUTION",
        target_type="PRODUCT",
        target_reference="prod_123",
        payload_json=json.dumps({"title": "Logitech Mouse", "price": 895}),
        status=InstructionStatus.AUTHORIZED,
        idempotency_key="idemp_1",
    )
    db_session.add(instruction)
    await db_session.commit()

    agent = MobileUseAgent()
    result = await agent.execute_instruction(
        db=db_session,
        instruction_id=instruction.id,
        requesting_membership_id=mem.id,
        family_id=fam.id,
    )

    assert result["status"] == "SUCCEEDED"
    assert result["is_simulated"] is True
    assert "no real purchase was made" in result["message"]

    # Verify task updated
    await db_session.refresh(task)
    assert task.status == PurchaseTaskStatus.COMPLETED
    assert task.execution_state == ExecutionState.SUCCEEDED


async def test_idempotent_duplicate_execution(db_session: AsyncSession, setup_family_and_admin):
    """Calling execute again on a SUCCEEDED instruction returns cached result idempotently."""
    fam, mem, task = setup_family_and_admin

    instruction = MobileUseInstruction(
        id=str(uuid.uuid4()),
        family_id=fam.id,
        purchase_task_id=task.id,
        created_by_agent="PurchaseAgent",
        action_type="SIMULATE_EXECUTION",
        target_type="PRODUCT",
        payload_json=json.dumps({"test": 1}),
        status=InstructionStatus.AUTHORIZED,
        idempotency_key="idemp_2",
    )
    db_session.add(instruction)
    await db_session.commit()

    agent = MobileUseAgent()
    # First run
    res1 = await agent.execute_instruction(
        db=db_session,
        instruction_id=instruction.id,
        requesting_membership_id=mem.id,
        family_id=fam.id,
    )
    assert res1["status"] == "SUCCEEDED"

    # Second run (idempotent)
    res2 = await agent.execute_instruction(
        db=db_session,
        instruction_id=instruction.id,
        requesting_membership_id=mem.id,
        family_id=fam.id,
    )
    assert res2["status"] == "SUCCEEDED"
    assert "idempotent" in res2["message"]


async def test_unknown_action_type_rejected(db_session: AsyncSession, setup_family_and_admin):
    """Unknown action types are rejected."""
    fam, mem, task = setup_family_and_admin

    instruction = MobileUseInstruction(
        id=str(uuid.uuid4()),
        family_id=fam.id,
        purchase_task_id=task.id,
        created_by_agent="PurchaseAgent",
        action_type="DANGEROUS_UNREGISTERED_ACTION",
        target_type="DEVICE",
        status=InstructionStatus.AUTHORIZED,
        idempotency_key="idemp_3",
    )
    db_session.add(instruction)
    await db_session.commit()

    agent = MobileUseAgent()
    with pytest.raises(InvalidInstruction):
        await agent.execute_instruction(
            db=db_session,
            instruction_id=instruction.id,
            requesting_membership_id=mem.id,
            family_id=fam.id,
        )


async def test_wrong_family_instruction_rejected(db_session: AsyncSession, setup_family_and_admin):
    """Instruction belonging to another family cannot be executed."""
    fam, mem, task = setup_family_and_admin

    instruction = MobileUseInstruction(
        id=str(uuid.uuid4()),
        family_id="other_family_uuid",
        purchase_task_id=task.id,
        created_by_agent="PurchaseAgent",
        action_type="SIMULATE_EXECUTION",
        target_type="PRODUCT",
        status=InstructionStatus.AUTHORIZED,
        idempotency_key="idemp_4",
    )
    db_session.add(instruction)
    await db_session.commit()

    agent = MobileUseAgent()
    with pytest.raises(NotFoundError):
        await agent.execute_instruction(
            db=db_session,
            instruction_id=instruction.id,
            requesting_membership_id=mem.id,
            family_id=fam.id,  # Admin's family is different
        )


async def test_qwen_mobile_execution_success(db_session: AsyncSession, setup_family_and_admin):
    """Qwen Mobile Agent executes visual grounding loop and strictly halts at hard payment boundary."""
    fam, mem, task = setup_family_and_admin

    instruction = MobileUseInstruction(
        id=str(uuid.uuid4()),
        family_id=fam.id,
        purchase_task_id=task.id,
        created_by_agent="PurchaseAgent",
        action_type="QWEN_MOBILE_EXECUTION",
        target_type="PRODUCT",
        target_reference="prod_qwen_1",
        payload_json=json.dumps({
            "title": "Logitech M235 Wireless Mouse",
            "price_amount": 895.0,
            "currency": "INR",
            "target_app": "Amazon Shopping",
            "specifications": {"DPI": 1000, "Connection": "USB Nano"},
        }),
        status=InstructionStatus.AUTHORIZED,
        idempotency_key="idemp_qwen_1",
    )
    db_session.add(instruction)
    await db_session.commit()

    agent = MobileUseAgent()
    result = await agent.execute_instruction(
        db=db_session,
        instruction_id=instruction.id,
        requesting_membership_id=mem.id,
        family_id=fam.id,
    )

    assert result["status"] == "SUCCEEDED"
    assert "Qwen Intelligence Mobile-Use Agent" in result["engine"]
    assert result["payment_boundary_enforced"] is True
    assert result["is_simulated"] is True

    # Validate the 7-step visual grounding trace
    trace = result["action_trace"]
    assert len(trace) == 7
    step_actions = [s["action"] for s in trace]
    assert step_actions == [
        "OPEN_APP",
        "GROUND_AND_TYPE",
        "GROUND_AND_TAP",
        "SWIPE_AND_INSPECT",
        "ADD_TO_CART",
        "NAVIGATE_TO_CHECKOUT",
        "PAUSE_FOR_USER_PAYMENT",
    ]

    # Verify the hard payment boundary step
    payment_step = trace[-1]
    assert payment_step["action"] == "PAUSE_FOR_USER_PAYMENT"
    assert payment_step["safety_boundary_enforced"] is True
    assert payment_step["status"] == "HALTED_FOR_SAFETY"
    assert "biometric" in payment_step["details"].lower()


async def test_qwen_mobile_agent_direct_grounding():
    """Direct execution of QwenMobileAgent returns valid viewport coordinates and bounding boxes."""
    from app.agents.qwen_mobile_agent import QwenMobileAgent

    qwen = QwenMobileAgent()
    res = await qwen.run_task(
        target_app="Flipkart",
        product_title="HP Wireless Mouse Z3700",
        price_amount=699.0,
        currency="INR",
        specifications={"DPI": 1200, "Color": "Blue"},
        mode_override="simulation",
    )

    assert res["status"] == "PAUSED_FOR_USER_CONFIRMATION"
    assert res["target_app"] == "Flipkart"
    assert res["viewport"] == {"width": 1080, "height": 2400}
    assert res["payment_boundary_enforced"] is True

    # Ensure search box grounding has valid bounding box coordinates
    search_step = res["action_trace"][1]
    assert search_step["element"] == "Search Box"
    assert len(search_step["coordinates"]) == 2
    assert len(search_step["bounding_box"]) == 4


async def test_adb_bridge_discovery():
    """ADBBridge correctly discovers bundled adb and queries version."""
    from app.agents.adb_bridge import ADBBridge

    bridge = ADBBridge()
    assert bridge.is_available() is True
    ver = await bridge.get_version()
    assert ver is not None
    assert "Android Debug Bridge" in ver


async def test_qwen_mobile_agent_adb_bridge_mode(monkeypatch):
    """QwenMobileAgent executes safely under mode='adb_bridge'."""
    from unittest.mock import AsyncMock
    from app.agents.adb_bridge import ADBBridge
    from app.agents.qwen_mobile_agent import QwenMobileAgent

    monkeypatch.setattr(ADBBridge, "list_devices", AsyncMock(return_value=[]))
    qwen = QwenMobileAgent()
    res = await qwen.run_task(
        target_app="Amazon Shopping",
        product_title="Wildcraft 30L School Bag",
        price_amount=899.0,
        currency="INR",
        specifications={"Capacity": "30L"},
        mode_override="adb_bridge",
    )

    assert res["status"] == "PAUSED_FOR_USER_CONFIRMATION"
    assert res["mode"] == "adb_bridge"
    assert res["payment_boundary_enforced"] is True
    assert len(res["action_trace"]) >= 6


async def test_extract_otp_from_bank_sms():
    """ADBBridge accurately extracts transaction OTPs from various bank SMS formats."""
    from app.agents.adb_bridge import ADBBridge

    # HDFC Bank
    sms1 = "Your OTP for transaction of INR 1,499.00 on your HDFC Bank Credit Card ending 4242 is 582910. Do not share OTP with anyone."
    assert ADBBridge.extract_otp_from_text(sms1, card_last4="4242") == "582910"

    # ICICI Bank
    sms2 = "481029 is the OTP to authenticate your payment of Rs 2,999 on ICICI Bank Credit Card ending 8891 at Amazon. Valid for 10 mins."
    assert ADBBridge.extract_otp_from_text(sms2, card_last4="8891") == "481029"

    # SBI Card
    sms3 = "Dear Customer, 912044 is the secret OTP for your credit card purchase of Rs 799 at AMAZON INDIA. NEVER SHARE OTP."
    assert ADBBridge.extract_otp_from_text(sms3) == "912044"

    # Axis Bank
    sms4 = "OTP: 739102. Valid for 5 mins. Use this code to approve your Amazon transaction of INR 450.00."
    assert ADBBridge.extract_otp_from_text(sms4) == "739102"

    # Short format
    sms5 = "Use code 391820 to complete your card purchase."
    assert ADBBridge.extract_otp_from_text(sms5) == "391820"

    # Notification text
    notif = "HDFC Bank: 628190 is your OTP for purchase at Amazon Pay"
    assert ADBBridge.extract_otp_from_text(notif) == "628190"


async def test_qwen_mobile_agent_credit_card_autonomous_flow():
    """QwenMobileAgent executes autonomous credit card flow including OTP and order placement."""
    from app.agents.qwen_mobile_agent import QwenMobileAgent

    qwen = QwenMobileAgent()
    res = await qwen.run_task(
        target_app="Amazon Shopping",
        product_title="Sony WH-1000XM5 Headphones",
        price_amount=26990.0,
        currency="INR",
        specifications={"Active Noise Cancellation": "Yes"},
        payment_details={
            "payment_mode": "CREDIT_CARD",
            "card_last4": "4242",
            "card_nickname": "HDFC Bank Regalia Credit Card",
            "cvv": "123",
        },
        mode_override="simulation",
    )

    assert res["status"] == "COMPLETED"
    assert res["payment_completed"] is True
    assert res["otp_verified"] is True
    assert res["payment_boundary_enforced"] is False

    actions = [step["action"] for step in res["action_trace"]]
    assert "SELECT_PAYMENT_METHOD" in actions
    assert "ENTER_CVV" in actions
    assert "PLACE_ORDER_AND_PAY" in actions
    assert "INTERCEPT_OTP" in actions
    assert "SUBMIT_3DS_OTP" in actions
    assert "ORDER_CONFIRMED" in actions


async def test_mobile_use_agent_credit_card_execution(db_session: AsyncSession, setup_family_and_admin, monkeypatch):
    """MobileUseAgent executes QWEN_MOBILE_EXECUTION with credit card details autonomously."""
    from unittest.mock import AsyncMock
    from app.agents.adb_bridge import ADBBridge
    monkeypatch.setattr(ADBBridge, "list_devices", AsyncMock(return_value=[]))
    fam, mem, task = setup_family_and_admin

    instruction = MobileUseInstruction(
        id=str(uuid.uuid4()),
        family_id=fam.id,
        purchase_task_id=task.id,
        created_by_agent="PurchaseAgent",
        action_type="QWEN_MOBILE_EXECUTION",
        target_type="PRODUCT",
        target_reference="prod_card_test",
        payload_json=json.dumps({
            "title": "Logitech MX Master 3S",
            "price_amount": 8995.0,
            "currency": "INR",
            "payment_mode": "CREDIT_CARD",
            "card_last4": "4242",
            "card_nickname": "HDFC Regalia",
            "cvv": "999",
        }),
        status=InstructionStatus.AUTHORIZED,
        idempotency_key="idemp_card_test_1",
    )
    db_session.add(instruction)
    await db_session.commit()

    agent = MobileUseAgent()
    result = await agent.execute_instruction(
        db=db_session,
        instruction_id=instruction.id,
        requesting_membership_id=mem.id,
        family_id=fam.id,
    )

    assert result["status"] == "SUCCEEDED"
    assert result["payment_completed"] is True
    assert result["payment_boundary_enforced"] is False
    actions = [step["action"] for step in result["action_trace"]]
    assert "SELECT_PAYMENT_METHOD" in actions
    assert "ENTER_CVV" in actions
    assert "INTERCEPT_OTP" in actions
    assert "SUBMIT_3DS_OTP" in actions



