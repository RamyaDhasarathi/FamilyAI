"""Purchase task and candidate lifecycle service."""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    ApprovalRequired,
    InvalidTaskState,
    NotFoundError,
    PermissionDenied,
    ValidationError,
)
from app.db.models.approval import ApprovalRequest, ApprovalStatus
from app.db.models.mobile_use import InstructionStatus, MobileUseInstruction
from app.db.models.purchase import (
    ApprovalState,
    ExecutionState,
    ProductCandidate,
    PurchaseTask,
    PurchaseTaskStatus,
    SourceType,
)
from app.policies.engine import PolicyEngine
from app.policies.rules import RA
from app.providers.products.factory import get_product_provider
from app.services.audit_service import AuditService

_engine = PolicyEngine()
_auditor = AuditService()


class PurchaseService:
    """Orchestrates purchase tasks, candidate discovery, selection, and execution prep."""

    async def create_task(
        self,
        db: AsyncSession,
        family_id: str,
        requester_membership_id: str,
        conversation_id: str,
        original_request: str,
        parsed_intent: Optional[Dict[str, Any]] = None,
        correlation_id: str = "task_create",
    ) -> PurchaseTask:
        """Create a new purchase task after FGP validation."""
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=requester_membership_id,
            family_id=family_id,
            resource=RA.PURCHASE_TASK_CREATE[0],
            action=RA.PURCHASE_TASK_CREATE[1],
            purpose="Create purchase task",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        task_id = str(uuid.uuid4())
        task = PurchaseTask(
            id=task_id,
            family_id=family_id,
            requester_membership_id=requester_membership_id,
            conversation_id=conversation_id,
            original_request=original_request,
            parsed_intent_json=json.dumps(parsed_intent or {}),
            status=PurchaseTaskStatus.RECEIVED,
            approval_state=ApprovalState.NOT_REQUIRED,
            execution_state=ExecutionState.NOT_STARTED,
        )
        db.add(task)
        await db.flush()

        await _auditor.log(
            db=db,
            family_id=family_id,
            actor_type="USER",
            actor_id=requester_membership_id,
            action="purchase.task.create",
            resource_type="purchase_task",
            resource_id=task_id,
            decision="ALLOW",
            reason_code=decision.reason_code,
            correlation_id=correlation_id,
            metadata={"original_request": original_request},
        )
        return task

    async def get_task(
        self,
        db: AsyncSession,
        task_id: str,
        requester_membership_id: str,
        family_id: str,
    ) -> PurchaseTask:
        """Retrieve a purchase task ensuring family scope and authorization."""
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=requester_membership_id,
            family_id=family_id,
            resource=RA.PURCHASE_TASK_READ[0],
            action=RA.PURCHASE_TASK_READ[1],
            purpose="Read purchase task",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        stmt = select(PurchaseTask).where(
            and_(
                PurchaseTask.id == task_id,
                PurchaseTask.family_id == family_id,
            )
        )
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise NotFoundError("PurchaseTask", task_id)

        # Enforce task ownership unless administrator
        from app.db.models.family import FamilyMembership, FamilyRole
        mem = await db.get(FamilyMembership, requester_membership_id)
        if mem and mem.family_role != FamilyRole.ADMIN and task.requester_membership_id != requester_membership_id:
            raise PermissionDenied("You can only access your own purchase tasks")

        return task

    async def list_user_tasks(
        self,
        db: AsyncSession,
        requester_membership_id: str,
        family_id: str,
    ) -> List[PurchaseTask]:
        """List tasks belonging to this user in the family."""
        stmt = (
            select(PurchaseTask)
            .where(
                and_(
                    PurchaseTask.family_id == family_id,
                    PurchaseTask.requester_membership_id == requester_membership_id,
                )
            )
            .order_by(PurchaseTask.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def search_and_save_candidates(
        self,
        db: AsyncSession,
        task: PurchaseTask,
        category: str,
        query: str,
        budget_amount: Optional[float] = None,
        currency: str = "INR",
        brand_preference: Optional[List[str]] = None,
        correlation_id: str = "search",
    ) -> List[ProductCandidate]:
        """Search products and persist candidates attached to this task."""
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=task.requester_membership_id,
            family_id=task.family_id,
            resource=RA.PURCHASE_CATALOGUE_SEARCH[0],
            action=RA.PURCHASE_CATALOGUE_SEARCH[1],
            purpose="Search product catalogue",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        provider = get_product_provider()
        results = await provider.search(
            category=category,
            query=query,
            budget_amount=budget_amount,
            currency=currency,
            brand_preference=brand_preference,
        )

        candidates: List[ProductCandidate] = []
        for r in results:
            cand_id = str(uuid.uuid4())
            cand = ProductCandidate(
                id=cand_id,
                purchase_task_id=task.id,
                provider="development_catalogue",
                provider_product_id=r.provider_product_id,
                title=r.title,
                brand=r.brand,
                price_amount=Decimal(str(r.price_amount)) if r.price_amount is not None else None,
                currency=r.currency,
                merchant=r.merchant,
                product_url=r.product_url,
                image_url=r.image_url,
                availability=r.availability,
                delivery_estimate=r.delivery_estimate,
                warranty_details=r.warranty_details,
                return_details=r.return_details,
                specifications_json=json.dumps(r.specifications),
                source_type=SourceType.DEVELOPMENT_CATALOGUE,
            )
            db.add(cand)
            candidates.append(cand)

        task.status = PurchaseTaskStatus.RECOMMENDATION_READY
        await db.flush()
        return candidates

    async def select_candidate(
        self,
        db: AsyncSession,
        task_id: str,
        product_id: str,
        requester_membership_id: str,
        family_id: str,
        correlation_id: str = "select",
    ) -> PurchaseTask:
        """Select a product candidate for this task."""
        task = await self.get_task(db, task_id, requester_membership_id, family_id)

        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=requester_membership_id,
            family_id=family_id,
            resource=RA.PURCHASE_PRODUCT_SELECT[0],
            action=RA.PURCHASE_PRODUCT_SELECT[1],
            purpose="Select product option",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        cand = await db.get(ProductCandidate, product_id)
        if not cand or cand.purchase_task_id != task.id:
            raise NotFoundError("ProductCandidate", product_id)

        task.selected_product_id = product_id
        task.status = PurchaseTaskStatus.OPTION_SELECTED
        await db.flush()

        await _auditor.log(
            db=db,
            family_id=family_id,
            actor_type="USER",
            actor_id=requester_membership_id,
            action="purchase.product.select",
            resource_type="purchase_task",
            resource_id=task_id,
            decision="ALLOW",
            reason_code="PRODUCT_SELECTED",
            correlation_id=correlation_id,
            metadata={"product_id": product_id, "product_title": cand.title},
        )
        return task

    async def prepare_execution(
        self,
        db: AsyncSession,
        task_id: str,
        requester_membership_id: str,
        family_id: str,
        correlation_id: str = "prepare_exec",
        action_type: Optional[str] = None,
        payment_mode: Optional[str] = "CREDIT_CARD",
        card_last4: Optional[str] = None,
        card_nickname: Optional[str] = None,
        cvv: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Prepare an execution instruction, enforcing approval policy."""
        task = await self.get_task(db, task_id, requester_membership_id, family_id)

        if not task.selected_product_id:
            raise ValidationError("A product candidate must be selected before preparing execution")

        cand = await db.get(ProductCandidate, task.selected_product_id)
        if not cand:
            raise NotFoundError("Selected ProductCandidate", str(task.selected_product_id))

        # Check prepare permission
        prep_decision = await _engine.evaluate(
            db=db,
            principal_membership_id=requester_membership_id,
            family_id=family_id,
            resource=RA.PURCHASE_EXECUTION_PREPARE[0],
            action=RA.PURCHASE_EXECUTION_PREPARE[1],
            purpose="Prepare purchase execution",
        )
        if prep_decision.effect == "DENY":
            raise PermissionDenied(prep_decision.human_readable_reason)

        # Check execution permission to see if approval is required
        exec_decision = await _engine.evaluate(
            db=db,
            principal_membership_id=requester_membership_id,
            family_id=family_id,
            resource=RA.PURCHASE_EXECUTION_EXECUTE[0],
            action=RA.PURCHASE_EXECUTION_EXECUTE[1],
            purpose="Execute purchase",
        )

        idempotency_key = f"exec_{task.id}_{task.selected_product_id}"

        # Return existing instruction if already prepared (idempotent)
        stmt_existing = select(MobileUseInstruction).where(
            MobileUseInstruction.family_id == family_id,
            MobileUseInstruction.idempotency_key == idempotency_key,
        )
        existing_res = await db.execute(stmt_existing)
        existing_instruction = existing_res.scalar_one_or_none()
        if existing_instruction:
            if existing_instruction.status == InstructionStatus.SUCCEEDED:
                existing_instruction.status = InstructionStatus.AUTHORIZED
            # Update existing instruction payload with latest payment configuration
            try:
                curr_payload = json.loads(existing_instruction.payload_json or "{}")
            except Exception:
                curr_payload = {}
            if payment_mode:
                curr_payload["payment_mode"] = payment_mode
            if card_last4:
                curr_payload["card_last4"] = card_last4
            if card_nickname:
                curr_payload["card_nickname"] = card_nickname
            if cvv:
                curr_payload["cvv"] = cvv
            existing_instruction.payload_json = json.dumps(curr_payload)
            await db.flush()
            return {
                "instruction_id": existing_instruction.id,
                "approval_required": existing_instruction.status == InstructionStatus.PENDING_APPROVAL,
                "approval_id": existing_instruction.approval_request_id,
                "status": existing_instruction.status.value,
                "message": "Execution instruction prepared and authorized",
            }

        instruction_id = str(uuid.uuid4())
        settings = get_settings()
        chosen_action = action_type or ("QWEN_MOBILE_EXECUTION" if getattr(settings, "QWEN_AGENT_ENABLED", True) else "SIMULATE_EXECUTION")

        specs = {}
        if cand.specifications_json:
            try:
                specs = json.loads(cand.specifications_json) if isinstance(cand.specifications_json, str) else cand.specifications_json
            except Exception:
                pass

        payload = {
            "task_id": task.id,
            "product_id": cand.id,
            "title": cand.title,
            "product_title": cand.title,
            "price_amount": float(cand.price_amount) if cand.price_amount is not None else None,
            "currency": cand.currency or "INR",
            "merchant": cand.merchant or "Shopping Provider",
            "target_app": cand.merchant or "Amazon Shopping",
            "specifications": specs,
            "payment_mode": payment_mode or "CREDIT_CARD",
            "card_last4": card_last4,
            "card_nickname": card_nickname,
            "cvv": cvv,
        }

        # If approval is required (effect == 'ASK' or approval_required == True)
        if exec_decision.effect == "ASK" or exec_decision.approval_required:
            approval_id = str(uuid.uuid4())
            approval = ApprovalRequest(
                id=approval_id,
                family_id=family_id,
                purchase_task_id=task.id,
                requested_by_membership_id=requester_membership_id,
                approval_type="PURCHASE_EXECUTION",
                status=ApprovalStatus.PENDING,
                request_payload_json=json.dumps(payload),
            )
            db.add(approval)

            instruction = MobileUseInstruction(
                id=instruction_id,
                family_id=family_id,
                purchase_task_id=task.id,
                created_by_agent="PurchaseAgent",
                action_type=chosen_action,
                target_type="PRODUCT",
                target_reference=cand.id,
                payload_json=json.dumps(payload),
                policy_decision_id=exec_decision.decision_id,
                approval_request_id=approval_id,
                status=InstructionStatus.PENDING_APPROVAL,
                idempotency_key=idempotency_key,
            )
            db.add(instruction)

            task.status = PurchaseTaskStatus.AWAITING_APPROVAL
            task.approval_state = ApprovalState.PENDING
            task.execution_state = ExecutionState.PREPARED
            await db.flush()

            await _auditor.log(
                db=db,
                family_id=family_id,
                actor_type="AGENT",
                actor_id="PurchaseAgent",
                action="approval.request.create",
                resource_type="approval_request",
                resource_id=approval_id,
                decision="ASK",
                reason_code="APPROVAL_REQUIRED",
                correlation_id=correlation_id,
            )

            return {
                "instruction_id": instruction_id,
                "approval_required": True,
                "approval_id": approval_id,
                "status": "PENDING_APPROVAL",
                "message": "Action prepared and awaiting administrator approval",
            }

        # Otherwise execution is directly authorized
        instruction = MobileUseInstruction(
            id=instruction_id,
            family_id=family_id,
            purchase_task_id=task.id,
            created_by_agent="PurchaseAgent",
            action_type=chosen_action,
            target_type="PRODUCT",
            target_reference=cand.id,
            payload_json=json.dumps(payload),
            policy_decision_id=exec_decision.decision_id,
            status=InstructionStatus.AUTHORIZED,
            idempotency_key=idempotency_key,
        )
        db.add(instruction)

        task.status = PurchaseTaskStatus.EXECUTION_PREPARED
        task.execution_state = ExecutionState.PREPARED
        await db.flush()

        return {
            "instruction_id": instruction_id,
            "approval_required": False,
            "status": "AUTHORIZED",
            "message": "Execution instruction prepared and authorized",
        }

    async def cancel_task(
        self,
        db: AsyncSession,
        task_id: str,
        requester_membership_id: str,
        family_id: str,
    ) -> PurchaseTask:
        """Cancel a purchase task."""
        task = await self.get_task(db, task_id, requester_membership_id, family_id)
        task.status = PurchaseTaskStatus.CANCELLED
        task.execution_state = ExecutionState.CANCELLED
        await db.flush()
        return task
