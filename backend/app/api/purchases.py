"""Purchase task and candidate endpoints."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_correlation_id, get_current_membership
from app.db.models.family import FamilyMembership
from app.db.models.purchase import ProductCandidate, PurchaseTask
from app.db.session import get_db
from app.schemas.purchase import (
    PrepareExecutionRequest,
    ProductCandidateResponse,
    PurchaseTaskResponse,
    SelectCandidateRequest,
)
from app.services.purchase_service import PurchaseService

router = APIRouter()
_purchase_service = PurchaseService()


def _to_task_response(t: PurchaseTask) -> PurchaseTaskResponse:
    status_str = t.status.value if hasattr(t.status, "value") else str(t.status)
    appr_str = t.approval_state.value if hasattr(t.approval_state, "value") else str(t.approval_state)
    exec_str = t.execution_state.value if hasattr(t.execution_state, "value") else str(t.execution_state)
    return PurchaseTaskResponse(
        id=t.id,
        family_id=t.family_id,
        conversation_id=t.conversation_id,
        original_request=t.original_request,
        status=status_str,
        budget_amount=float(t.budget_amount) if t.budget_amount is not None else None,
        currency=t.currency,
        selected_product_id=t.selected_product_id,
        approval_state=appr_str,
        execution_state=exec_str,
        created_at=t.created_at.isoformat(),
        updated_at=t.updated_at.isoformat(),
    )


@router.get("", response_model=List[PurchaseTaskResponse])
async def list_tasks(
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """List purchase tasks created by the authenticated member."""
    tasks = await _purchase_service.list_user_tasks(
        db=db,
        requester_membership_id=membership.id,
        family_id=membership.family_id,
    )
    return [_to_task_response(t) for t in tasks]


@router.post("", response_model=PurchaseTaskResponse)
async def create_task(
    payload: Dict[str, Any],
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Explicitly create a new purchase task."""
    task = await _purchase_service.create_task(
        db=db,
        family_id=membership.family_id,
        requester_membership_id=membership.id,
        conversation_id=payload.get("conversation_id", ""),
        original_request=payload.get("original_request", ""),
        parsed_intent=payload.get("parsed_intent"),
        correlation_id=correlation_id,
    )
    return _to_task_response(task)


@router.get("/{task_id}", response_model=PurchaseTaskResponse)
async def get_task(
    task_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details of a purchase task."""
    task = await _purchase_service.get_task(
        db=db,
        task_id=task_id,
        requester_membership_id=membership.id,
        family_id=membership.family_id,
    )
    return _to_task_response(task)


@router.get("/{task_id}/candidates", response_model=List[ProductCandidateResponse])
async def get_candidates(
    task_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve discovered product candidates for a task."""
    task = await _purchase_service.get_task(
        db=db,
        task_id=task_id,
        requester_membership_id=membership.id,
        family_id=membership.family_id,
    )
    stmt = (
        select(ProductCandidate)
        .where(ProductCandidate.purchase_task_id == task.id)
        .order_by(ProductCandidate.created_at.asc())
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    out = []
    for c in candidates:
        specs = {}
        if c.specifications_json:
            try:
                specs = json.loads(c.specifications_json)
            except Exception:
                pass
        src_str = c.source_type.value if hasattr(c.source_type, "value") else str(c.source_type)
        out.append(
            ProductCandidateResponse(
                id=c.id,
                title=c.title,
                brand=c.brand,
                price_amount=float(c.price_amount) if c.price_amount is not None else None,
                currency=c.currency,
                merchant=c.merchant,
                product_url=c.product_url,
                image_url=c.image_url,
                availability=c.availability,
                delivery_estimate=c.delivery_estimate,
                warranty_details=c.warranty_details,
                return_details=c.return_details,
                specifications_json=specs,
                source_type=src_str,
                provider=c.provider,
                last_checked_at=c.last_checked_at.isoformat() if c.last_checked_at else None,
            )
        )
    return out


@router.post("/{task_id}/select", response_model=PurchaseTaskResponse)
async def select_candidate(
    task_id: str,
    req: SelectCandidateRequest,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Select a product candidate for this task."""
    task = await _purchase_service.select_candidate(
        db=db,
        task_id=task_id,
        product_id=req.product_id,
        requester_membership_id=membership.id,
        family_id=membership.family_id,
        correlation_id=correlation_id,
    )
    return _to_task_response(task)


@router.post("/{task_id}/prepare-execution")
async def prepare_execution(
    task_id: str,
    req: Optional[PrepareExecutionRequest] = None,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Prepare an execution instruction, checking approval requirements."""
    return await _purchase_service.prepare_execution(
        db=db,
        task_id=task_id,
        requester_membership_id=membership.id,
        family_id=membership.family_id,
        correlation_id=correlation_id,
        action_type=req.action_type if req else None,
        payment_mode=req.payment_mode if req else "CREDIT_CARD",
        card_last4=req.card_last4 if req else None,
        card_nickname=req.card_nickname if req else None,
        cvv=req.cvv if req else None,
    )


@router.post("/{task_id}/cancel", response_model=PurchaseTaskResponse)
async def cancel_task(
    task_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a purchase task."""
    task = await _purchase_service.cancel_task(
        db=db,
        task_id=task_id,
        requester_membership_id=membership.id,
        family_id=membership.family_id,
    )
    return _to_task_response(task)
