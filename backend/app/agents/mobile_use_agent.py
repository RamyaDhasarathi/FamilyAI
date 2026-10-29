"""Mobile Use Agent — executes authorized mobile actions with strict governance."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ApprovalRequired,
    DuplicateExecution,
    InstructionExpired,
    InvalidInstruction,
    NotFoundError,
    PermissionDenied,
    PolicyChanged,
)
from app.db.models.approval import ApprovalRequest, ApprovalStatus
from app.db.models.mobile_use import InstructionStatus, MobileUseInstruction
from app.db.models.purchase import ExecutionState, PurchaseTask, PurchaseTaskStatus
from app.policies.engine import PolicyEngine
from app.policies.rules import RA
from app.services.audit_service import AuditService

_engine = PolicyEngine()
_auditor = AuditService()

from app.agents.qwen_mobile_agent import QwenMobileAgent

SUPPORTED_ACTIONS = {
    "SIMULATE_EXECUTION",
    "OPEN_PRODUCT_URL",
    "PREPARE_PURCHASE",
    "QWEN_MOBILE_EXECUTION",
}


class MobileUseAgent:
    """Safely executes authorized instructions on behalf of the family."""

    async def execute_instruction(
        self,
        db: AsyncSession,
        instruction_id: str,
        requesting_membership_id: str,
        family_id: str,
        correlation_id: str = "mobile_exec",
    ) -> Dict[str, Any]:
        """Execute a registered instruction following FGP re-evaluation and approval verification."""
        # 1. Fetch instruction
        stmt = select(MobileUseInstruction).where(
            MobileUseInstruction.id == instruction_id,
            MobileUseInstruction.family_id == family_id,
        )
        result = await db.execute(stmt)
        instruction = result.scalar_one_or_none()
        if not instruction:
            raise NotFoundError("MobileUseInstruction", instruction_id)

        # 2. Idempotency check: allow re-execution for real device grounding
        if instruction.status == InstructionStatus.SUCCEEDED and instruction.action_type != "QWEN_MOBILE_EXECUTION":
            return {
                "instruction_id": instruction.id,
                "status": "SUCCEEDED",
                "action_type": instruction.action_type,
                "message": "Instruction was already executed successfully (idempotent result).",
                "is_simulated": True,
                "notice": "Simulation completed — no real purchase was made.",
            }

        # 3. Check status is AUTHORIZED
        if instruction.status == InstructionStatus.PENDING_APPROVAL:
            raise ApprovalRequired(approval_id=str(instruction.approval_request_id))

        if instruction.status in (InstructionStatus.CANCELLED, InstructionStatus.FAILED, InstructionStatus.EXPIRED):
            raise InvalidInstruction(f"Instruction is in terminal state '{instruction.status.value}'")

        # 4. Check approval validity if linked to an approval request
        if instruction.approval_request_id:
            approval = await db.get(ApprovalRequest, instruction.approval_request_id)
            if not approval or approval.status != ApprovalStatus.APPROVED:
                raise ApprovalRequired("Linked approval is not approved")
            if approval.expires_at and approval.expires_at < datetime.now(timezone.utc):
                instruction.status = InstructionStatus.EXPIRED
                await db.flush()
                raise InstructionExpired()

        # 5. Re-evaluate FGP policy right before execution (prevent race condition / stale grants)
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=requesting_membership_id,
            family_id=family_id,
            resource=RA.MOBILE_USE_INSTRUCTION_EXECUTE[0],
            action=RA.MOBILE_USE_INSTRUCTION_EXECUTE[1],
            purpose="Execute mobile use instruction",
        )
        if decision.effect == "DENY":
            instruction.status = InstructionStatus.FAILED
            await db.flush()
            raise PermissionDenied(f"Policy denial before execution: {decision.human_readable_reason}")

        # 6. Validate action type
        action_type = instruction.action_type.upper()
        if action_type not in SUPPORTED_ACTIONS:
            instruction.status = InstructionStatus.FAILED
            await db.flush()
            raise InvalidInstruction(f"Unknown action type '{instruction.action_type}'. Supported: {SUPPORTED_ACTIONS}")

        payload = json.loads(instruction.payload_json or "{}")
        is_sim = True
        notice_msg = "Simulation completed — no real purchase was made."

        # 7. Execute according to action type
        instruction.status = InstructionStatus.EXECUTING
        await db.flush()

        task = await db.get(PurchaseTask, instruction.purchase_task_id)

        if action_type == "SIMULATE_EXECUTION":
            # Local execution simulation: explicitly states no money was spent
            instruction.status = InstructionStatus.SUCCEEDED
            if task:
                task.status = PurchaseTaskStatus.COMPLETED
                task.execution_state = ExecutionState.SUCCEEDED

            exec_result = {
                "instruction_id": instruction.id,
                "status": "SUCCEEDED",
                "action_type": action_type,
                "simulation_id": f"sim_{instruction.id[:8]}",
                "message": "Simulation completed — no real purchase was made.",
                "is_simulated": True,
                "payload": payload,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

        elif action_type == "OPEN_PRODUCT_URL":
            # Validates URL scheme safely
            url = payload.get("url") or payload.get("product_url")
            if url:
                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https"):
                    raise InvalidInstruction("Invalid or unsafe URL scheme")

            instruction.status = InstructionStatus.SUCCEEDED
            if task:
                task.status = PurchaseTaskStatus.COMPLETED
                task.execution_state = ExecutionState.SUCCEEDED

            exec_result = {
                "instruction_id": instruction.id,
                "status": "SUCCEEDED",
                "action_type": action_type,
                "target_url": url,
                "message": f"Product URL validated: {url or 'Development link'}",
                "is_simulated": True,
                "notice": "Simulation completed — no real purchase was made.",
            }

        elif action_type == "PREPARE_PURCHASE":
            instruction.status = InstructionStatus.SUCCEEDED
            if task:
                task.execution_state = ExecutionState.PREPARED

            exec_result = {
                "instruction_id": instruction.id,
                "status": "SUCCEEDED",
                "action_type": action_type,
                "message": "Purchase record prepared for manual user review.",
                "is_simulated": True,
                "notice": "Simulation completed — no real purchase was made.",
            }

        elif action_type == "QWEN_MOBILE_EXECUTION":
            # Run Qwen Intelligence Mobile-Use Agent with grounding and safety boundary
            instruction.status = InstructionStatus.SUCCEEDED
            if task:
                task.status = PurchaseTaskStatus.COMPLETED
                task.execution_state = ExecutionState.SUCCEEDED

            # Release SQLite write transaction before running long phone automation
            await db.commit()

            qwen = QwenMobileAgent()
            target_app = payload.get("target_app") or payload.get("merchant") or "Amazon Shopping"
            product_title = (
                payload.get("title")
                or payload.get("product_title")
                or (task.original_request if task else "Product Candidate")
            )
            price_amount = payload.get("price_amount")
            currency = payload.get("currency") or "INR"
            specs = payload.get("specifications") or {}
            payment_details = None
            if payload.get("payment_mode"):
                payment_details = {
                    "payment_mode": payload.get("payment_mode"),
                    "card_last4": payload.get("card_last4"),
                    "card_nickname": payload.get("card_nickname"),
                    "cvv": payload.get("cvv"),
                }

            qwen_res = await qwen.run_task(
                target_app=target_app,
                product_title=product_title,
                price_amount=price_amount,
                currency=currency,
                specifications=specs,
                payment_details=payment_details,
            )

            is_sim = qwen_res.get("is_simulated", False)
            notice_msg = qwen_res.get("notice", "Autonomous checkout executed on phone — credit card payment and OTP verified.")

            exec_result = {
                "instruction_id": instruction.id,
                "status": "SUCCEEDED",
                "action_type": action_type,
                "engine": qwen_res["engine"],
                "message": qwen_res["message"],
                "qwen_status": qwen_res["status"],
                "payment_boundary_enforced": qwen_res.get("payment_boundary_enforced", False),
                "payment_completed": qwen_res.get("payment_completed", True),
                "otp_verified": qwen_res.get("otp_verified", False),
                "action_trace": qwen_res["action_trace"],
                "is_simulated": is_sim,
                "notice": notice_msg,
                "details": qwen_res,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

        await db.flush()

        await _auditor.log(
            db=db,
            family_id=family_id,
            actor_type="AGENT",
            actor_id="MobileUseAgent",
            action=f"mobile_use.instruction.execute.{action_type.lower()}",
            resource_type="mobile_use_instruction",
            resource_id=instruction.id,
            decision="ALLOW",
            reason_code="EXECUTION_SUCCESS" if not is_sim else "EXECUTION_SIMULATION_SUCCESS",
            correlation_id=correlation_id,
            metadata={
                "is_simulated": is_sim,
                "notice": notice_msg,
                "action_trace": exec_result.get("action_trace", []),
                "payment_completed": exec_result.get("payment_completed", False),
                "otp_verified": exec_result.get("otp_verified", False),
            },
        )

        return exec_result
