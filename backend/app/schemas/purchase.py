"""Purchase task and product candidate Pydantic schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Payload for sending a chat message to an agent."""

    conversation_id: Optional[str] = None
    message: str
    task_id: Optional[str] = None


class ProductCandidateResponse(BaseModel):
    """A single product candidate surfaced by the Purchase Agent."""

    id: str
    title: str
    brand: Optional[str] = None
    price_amount: Optional[float] = None
    currency: Optional[str] = None
    merchant: Optional[str] = None
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    availability: Optional[str] = None
    delivery_estimate: Optional[str] = None
    warranty_details: Optional[str] = None
    return_details: Optional[str] = None
    specifications_json: dict = {}
    source_type: str
    provider: str
    last_checked_at: Optional[str] = None
    score: Optional[float] = None
    rank: Optional[int] = None


class ChatResponse(BaseModel):
    """Response returned after an agent chat turn."""

    conversation_id: str
    message_id: str
    agent_type: str
    reply: str
    task_id: Optional[str] = None
    task_status: Optional[str] = None
    structured_response: Optional[dict] = None
    candidates: Optional[list[ProductCandidateResponse]] = None
    available_actions: list[str] = []
    correlation_id: str
    is_development_data: bool = False


class PurchaseTaskResponse(BaseModel):
    """Serialised purchase-task record."""

    id: str
    family_id: str
    conversation_id: Optional[str] = None
    original_request: str
    status: str
    budget_amount: Optional[float] = None
    currency: Optional[str] = None
    selected_product_id: Optional[str] = None
    approval_state: str
    execution_state: str
    created_at: str
    updated_at: str


class SelectCandidateRequest(BaseModel):
    """Payload to select a product candidate for a task."""

    product_id: str


class PrepareExecutionRequest(BaseModel):
    """Payload to prepare mobile execution, including payment specifications."""

    payment_mode: Optional[str] = "CREDIT_CARD"
    card_last4: Optional[str] = None
    card_nickname: Optional[str] = None
    cvv: Optional[str] = None
    action_type: Optional[str] = None

