"""Approval workflow service for Family OS."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ApprovalExpired,
    NotFoundError,
    PermissionDenied,
    ValidationError,
)
from app.db.models.approval import ApprovalRequest, ApprovalStatus
from app.db.models.mobile_use import InstructionStatus, MobileUseInstruction
from app.db.models.purchase import ApprovalState, PurchaseTask, PurchaseTaskStatus
from app.policies.engine import PolicyEngine
from app.policies.rules import RA
from app.services.audit_service import AuditService

_engine = PolicyEngine()
_auditor = AuditService()


class ApprovalService:
    """Manages creation, review, approval, and rejection of sensitive actions."""

    async def get_pending(
        self,
        db: AsyncSession,
        membership_id: str,
        family_id: str,
    ) -> List[ApprovalRequest]:
        """List all pending approval requests in the family."""
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=membership_id,
            family_id=family_id,
            resource=RA.APPROVAL_REQUEST_READ[0],
            action=RA.APPROVAL_REQUEST_READ[1],
            purpose="Read pending approvals",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        stmt = (
            select(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.family_id == family_id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
            )
            .order_by(ApprovalRequest.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_approval(
        self,
        db: AsyncSession,
        approval_id: str,
        membership_id: str,
        family_id: str,
    ) -> ApprovalRequest:
        """Get an approval request by ID."""
        stmt = select(ApprovalRequest).where(
            and_(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.family_id == family_id,
            )
        )
        result = await db.execute(stmt)
        approval = result.scalar_one_or_none()
        if not approval:
            raise NotFoundError("ApprovalRequest", approval_id)
        return approval

    async def approve(
        self,
        db: AsyncSession,
        approval_id: str,
        approver_membership_id: str,
        family_id: str,
        reason: Optional[str] = None,
        correlation_id: str = "approve",
    ) -> ApprovalRequest:
        """Approve a pending action."""
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=approver_membership_id,
            family_id=family_id,
            resource=RA.APPROVAL_REQUEST_DECIDE[0],
            action=RA.APPROVAL_REQUEST_DECIDE[1],
            purpose="Approve request",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        approval = await self.get_approval(db, approval_id, approver_membership_id, family_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ValidationError(f"Cannot approve request in status {approval.status}")

        if approval.expires_at and approval.expires_at < datetime.now(timezone.utc):
            approval.status = ApprovalStatus.EXPIRED
            await db.flush()
            raise ApprovalExpired()

        approval.status = ApprovalStatus.APPROVED
        approval.approver_membership_id = approver_membership_id
        approval.decision_reason = reason or "Approved by family administrator"
        approval.decided_at = datetime.now(timezone.utc)

        # Update linked MobileUseInstruction to AUTHORIZED
        instr_stmt = select(MobileUseInstruction).where(
            MobileUseInstruction.approval_request_id == approval_id
        )
        instr_res = await db.execute(instr_stmt)
        instruction = instr_res.scalar_one_or_none()
        if instruction:
            instruction.status = InstructionStatus.AUTHORIZED

        # Update linked PurchaseTask
        task = await db.get(PurchaseTask, approval.purchase_task_id)
        if task:
            task.approval_state = ApprovalState.APPROVED
            task.status = PurchaseTaskStatus.APPROVED

        await db.flush()

        await _auditor.log(
            db=db,
            family_id=family_id,
            actor_type="USER",
            actor_id=approver_membership_id,
            action="approval.request.approve",
            resource_type="approval_request",
            resource_id=approval_id,
            decision="ALLOW",
            reason_code="APPROVED",
            correlation_id=correlation_id,
            metadata={"decision_reason": approval.decision_reason},
        )
        return approval

    async def deny(
        self,
        db: AsyncSession,
        approval_id: str,
        approver_membership_id: str,
        family_id: str,
        reason: Optional[str] = None,
        correlation_id: str = "deny",
    ) -> ApprovalRequest:
        """Deny a pending action."""
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=approver_membership_id,
            family_id=family_id,
            resource=RA.APPROVAL_REQUEST_DECIDE[0],
            action=RA.APPROVAL_REQUEST_DECIDE[1],
            purpose="Deny request",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        approval = await self.get_approval(db, approval_id, approver_membership_id, family_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ValidationError(f"Cannot deny request in status {approval.status}")

        approval.status = ApprovalStatus.DENIED
        approval.approver_membership_id = approver_membership_id
        approval.decision_reason = reason or "Denied by family administrator"
        approval.decided_at = datetime.now(timezone.utc)

        # Cancel linked MobileUseInstruction
        instr_stmt = select(MobileUseInstruction).where(
            MobileUseInstruction.approval_request_id == approval_id
        )
        instr_res = await db.execute(instr_stmt)
        instruction = instr_res.scalar_one_or_none()
        if instruction:
            instruction.status = InstructionStatus.CANCELLED

        # Update linked PurchaseTask
        task = await db.get(PurchaseTask, approval.purchase_task_id)
        if task:
            task.approval_state = ApprovalState.DENIED
            task.status = PurchaseTaskStatus.CANCELLED

        await db.flush()

        await _auditor.log(
            db=db,
            family_id=family_id,
            actor_type="USER",
            actor_id=approver_membership_id,
            action="approval.request.deny",
            resource_type="approval_request",
            resource_id=approval_id,
            decision="DENY",
            reason_code="DENIED",
            correlation_id=correlation_id,
            metadata={"decision_reason": approval.decision_reason},
        )
        return approval

    async def cancel(
        self,
        db: AsyncSession,
        approval_id: str,
        membership_id: str,
        family_id: str,
    ) -> ApprovalRequest:
        """Cancel an approval request by requester or admin."""
        approval = await self.get_approval(db, approval_id, membership_id, family_id)
        approval.status = ApprovalStatus.CANCELLED
        await db.flush()
        return approval
