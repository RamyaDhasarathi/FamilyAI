"""Mobile Use Agent API endpoints."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.adb_bridge import ADBBridge
from app.agents.mobile_use_agent import MobileUseAgent
from app.core.dependencies import get_correlation_id, get_current_membership
from app.db.models.family import FamilyMembership
from app.db.models.mobile_use import MobileUseInstruction
from app.db.session import get_db
from app.schemas.mobile_use import (
    ConnectDeviceRequest,
    ExecuteInstructionRequest,
    MobileUseInstructionResponse,
)
from app.services.mobile_use_service import MobileUseService

router = APIRouter()
_mobile_service = MobileUseService()
_mobile_agent = MobileUseAgent()


def _to_instruction_response(i: MobileUseInstruction) -> MobileUseInstructionResponse:
    payload = {}
    if i.payload_json:
        try:
            payload = json.loads(i.payload_json)
        except Exception:
            pass
    status_str = i.status.value if hasattr(i.status, "value") else str(i.status)
    return MobileUseInstructionResponse(
        id=i.id,
        family_id=i.family_id,
        purchase_task_id=i.purchase_task_id,
        created_by_agent=i.created_by_agent,
        action_type=i.action_type,
        target_type=i.target_type,
        target_reference=i.target_reference,
        payload_json=payload,
        policy_decision_id=i.policy_decision_id,
        approval_request_id=i.approval_request_id,
        status=status_str,
        idempotency_key=i.idempotency_key,
        created_at=i.created_at.isoformat(),
        updated_at=i.updated_at.isoformat(),
    )


@router.get("/instructions", response_model=List[MobileUseInstructionResponse])
async def list_instructions(
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """List execution instructions in this family."""
    instructions = await _mobile_service.list_instructions(
        db=db,
        membership_id=membership.id,
        family_id=membership.family_id,
    )
    return [_to_instruction_response(i) for i in instructions]


@router.get("/instructions/{instruction_id}", response_model=MobileUseInstructionResponse)
async def get_instruction(
    instruction_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details of an instruction."""
    instruction = await _mobile_service.get_instruction(
        db=db,
        instruction_id=instruction_id,
        membership_id=membership.id,
        family_id=membership.family_id,
    )
    return _to_instruction_response(instruction)


@router.post("/instructions/{instruction_id}/execute")
async def execute_instruction(
    instruction_id: str,
    req: Optional[ExecuteInstructionRequest] = None,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
) -> Dict[str, Any]:
    """Trigger execution of an authorized mobile instruction."""
    return await _mobile_agent.execute_instruction(
        db=db,
        instruction_id=instruction_id,
        requesting_membership_id=membership.id,
        family_id=membership.family_id,
        correlation_id=correlation_id,
    )


@router.post("/instructions/{instruction_id}/cancel", response_model=MobileUseInstructionResponse)
async def cancel_instruction(
    instruction_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an unexecuted instruction."""
    instruction = await _mobile_service.cancel_instruction(
        db=db,
        instruction_id=instruction_id,
        membership_id=membership.id,
        family_id=membership.family_id,
    )
    return _to_instruction_response(instruction)


@router.get("/devices")
async def list_adb_devices(
    membership: FamilyMembership = Depends(get_current_membership),
) -> Dict[str, Any]:
    """List connected Android ADB devices (Wi-Fi or USB)."""
    bridge = ADBBridge()
    available = bridge.is_available()
    version = await bridge.get_version() if available else None
    devices = await bridge.list_devices() if available else []
    return {
        "adb_available": available,
        "adb_version": version,
        "devices": devices,
        "active_serial": bridge.default_serial,
    }


@router.post("/devices/connect")
async def connect_adb_device(
    req: ConnectDeviceRequest,
    membership: FamilyMembership = Depends(get_current_membership),
) -> Dict[str, Any]:
    """Connect to a physical Android device over Wi-Fi via ADB."""
    bridge = ADBBridge()
    return await bridge.connect(req.host_port)


@router.post("/devices/disconnect")
async def disconnect_adb_device(
    req: Optional[ConnectDeviceRequest] = None,
    membership: FamilyMembership = Depends(get_current_membership),
) -> Dict[str, Any]:
    """Disconnect a wireless Android device."""
    bridge = ADBBridge()
    target = req.host_port if req else None
    return await bridge.disconnect(target)

