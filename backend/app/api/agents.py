"""Agent registry and conversational chat endpoints."""
from __future__ import annotations

import json
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.purchase_agent import PurchaseAgent
from app.core.dependencies import get_correlation_id, get_current_membership
from app.core.exceptions import AppError, NotFoundError, PermissionDenied
from app.db.models.conversation import AgentType, Conversation, Message
from app.db.models.family import FamilyMembership
from app.db.session import get_db
from app.schemas.purchase import ChatRequest, ChatResponse

router = APIRouter()
_purchase_agent = PurchaseAgent()


@router.get("/agents")
async def list_agents() -> List[Dict[str, Any]]:
    """List available and planned Family OS agents."""
    return [
        {
            "type": "PURCHASE",
            "name": "Purchase Agent",
            "status": "available",
            "description": "Helps you research, compare, and prepare product purchases within family guidelines.",
        },
        {
            "type": "TRAVEL",
            "name": "Travel Agent",
            "status": "planned",
            "description": "Travel Agent is planned but is not implemented in this release.",
        },
    ]


@router.post("/agents/{agent_type}/chat", response_model=ChatResponse)
async def chat_with_agent(
    agent_type: str,
    req: ChatRequest,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Send a message to an agent and receive a structured reply."""
    agent_upper = agent_type.upper()
    if agent_upper == "TRAVEL":
        raise AppError(
            code="AGENT_UNAVAILABLE",
            message="Travel Agent is planned but is not implemented in this release.",
            status_code=503,
        )

    if agent_upper != "PURCHASE":
        raise AppError(
            code="UNKNOWN_AGENT",
            message=f"Agent '{agent_type}' is unknown.",
            status_code=404,
        )

    res = await _purchase_agent.process_message(
        db=db,
        conversation_id=req.conversation_id,
        user_message=req.message,
        task_id=req.task_id,
        membership=membership,
        correlation_id=correlation_id,
    )
    return res


@router.get("/conversations")
async def list_conversations(
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List conversations belonging to the authenticated family member."""
    stmt = (
        select(Conversation)
        .where(
            Conversation.family_id == membership.family_id,
            Conversation.owner_membership_id == membership.id,
        )
        .order_by(Conversation.updated_at.desc())
    )
    result = await db.execute(stmt)
    convs = result.scalars().all()
    return [
        {
            "id": c.id,
            "agent_type": c.agent_type.value if hasattr(c.agent_type, "value") else str(c.agent_type),
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in convs
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve details of a specific conversation."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.family_id == membership.family_id,
    )
    res = await db.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation", conversation_id)

    return {
        "id": conv.id,
        "agent_type": conv.agent_type.value if hasattr(conv.agent_type, "value") else str(conv.agent_type),
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Retrieve messages in a conversation."""
    # Ensure conversation belongs to family & member
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.family_id == membership.family_id,
    )
    res = await db.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation", conversation_id)

    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    msg_res = await db.execute(msg_stmt)
    messages = msg_res.scalars().all()

    out = []
    for m in messages:
        meta = {}
        if m.metadata_json:
            try:
                meta = json.loads(m.metadata_json)
            except Exception:
                pass
        out.append({
            "id": m.id,
            "sender_type": m.sender_type.value if hasattr(m.sender_type, "value") else str(m.sender_type),
            "content": m.content,
            "content_type": m.content_type.value if hasattr(m.content_type, "value") else str(m.content_type),
            "metadata_json": meta,
            "created_at": m.created_at.isoformat(),
        })
    return out
