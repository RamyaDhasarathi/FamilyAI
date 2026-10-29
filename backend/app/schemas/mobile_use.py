"""Mobile Use Agent instruction Pydantic schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MobileUseInstructionResponse(BaseModel):
    """Serialised mobile-use instruction record."""

    id: str
    family_id: str
    purchase_task_id: str
    created_by_agent: str
    action_type: str
    target_type: str
    target_reference: Optional[str]
    payload_json: dict
    policy_decision_id: Optional[str]
    approval_request_id: Optional[str]
    status: str
    idempotency_key: str
    created_at: str
    updated_at: str


class ExecuteInstructionRequest(BaseModel):
    """Optional metadata supplied when triggering instruction execution."""

    idempotency_key: Optional[str] = None
    override_reason: Optional[str] = None


class ConnectDeviceRequest(BaseModel):
    """Parameters for connecting to an Android device over ADB Wi-Fi."""

    host_port: str
