"""PurchaseTask and ProductCandidate models for Family OS."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, MappedColumn, relationship

from app.db.base import Base, UUIDMixin


class PurchaseTaskStatus(str, enum.Enum):
    """Full lifecycle status of a purchase task."""

    RECEIVED = "RECEIVED"
    UNDERSTANDING_REQUEST = "UNDERSTANDING_REQUEST"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    SEARCHING = "SEARCHING"
    COMPARING = "COMPARING"
    RECOMMENDATION_READY = "RECOMMENDATION_READY"
    AWAITING_USER_SELECTION = "AWAITING_USER_SELECTION"
    OPTION_SELECTED = "OPTION_SELECTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTION_PREPARED = "EXECUTION_PREPARED"
    HANDED_TO_MOBILE_USE = "HANDED_TO_MOBILE_USE"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ApprovalState(str, enum.Enum):
    """Approval sub-state of a purchase task."""

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class ExecutionState(str, enum.Enum):
    """Execution sub-state of a purchase task."""

    NOT_STARTED = "NOT_STARTED"
    PREPARED = "PREPARED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SourceType(str, enum.Enum):
    """How a product candidate was sourced."""

    REAL_PROVIDER = "REAL_PROVIDER"
    DEVELOPMENT_CATALOGUE = "DEVELOPMENT_CATALOGUE"


class PurchaseTask(UUIDMixin, Base):
    """Represents a single end-to-end purchase request orchestrated by the agent."""

    __tablename__ = "purchase_tasks"

    family_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requester_membership_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("family_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    beneficiary_membership_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("family_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_request: MappedColumn[str] = mapped_column(Text, nullable=False)
    parsed_intent_json: MappedColumn[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    status: MappedColumn[PurchaseTaskStatus] = mapped_column(
        SAEnum(PurchaseTaskStatus, name="purchase_task_status_enum"),
        default=PurchaseTaskStatus.RECEIVED,
        nullable=False,
        index=True,
    )
    budget_amount: MappedColumn[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    currency: MappedColumn[Optional[str]] = mapped_column(
        String(3),
        nullable=True,
    )
    selected_product_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )
    approval_state: MappedColumn[ApprovalState] = mapped_column(
        SAEnum(ApprovalState, name="approval_state_enum"),
        default=ApprovalState.NOT_REQUIRED,
        nullable=False,
    )
    execution_state: MappedColumn[ExecutionState] = mapped_column(
        SAEnum(ExecutionState, name="execution_state_enum"),
        default=ExecutionState.NOT_STARTED,
        nullable=False,
    )
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    product_candidates: Mapped[list["ProductCandidate"]] = relationship(
        "ProductCandidate",
        back_populates="purchase_task",
        cascade="all, delete-orphan",
    )
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ApprovalRequest",
        back_populates="purchase_task",
        cascade="all, delete-orphan",
    )
    mobile_use_instructions: Mapped[list["MobileUseInstruction"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "MobileUseInstruction",
        back_populates="purchase_task",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<PurchaseTask id={self.id!r} family_id={self.family_id!r} "
            f"status={self.status!r}>"
        )


class ProductCandidate(UUIDMixin, Base):
    """A product surfaced by the agent as a candidate for a PurchaseTask."""

    __tablename__ = "product_candidates"

    purchase_task_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("purchase_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: MappedColumn[str] = mapped_column(String(255), nullable=False)
    provider_product_id: MappedColumn[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    title: MappedColumn[str] = mapped_column(String(512), nullable=False)
    brand: MappedColumn[Optional[str]] = mapped_column(String(255), nullable=True)
    price_amount: MappedColumn[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    currency: MappedColumn[Optional[str]] = mapped_column(String(3), nullable=True)
    merchant: MappedColumn[Optional[str]] = mapped_column(String(255), nullable=True)
    product_url: MappedColumn[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: MappedColumn[Optional[str]] = mapped_column(Text, nullable=True)
    availability: MappedColumn[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_estimate: MappedColumn[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    warranty_details: MappedColumn[Optional[str]] = mapped_column(Text, nullable=True)
    return_details: MappedColumn[Optional[str]] = mapped_column(Text, nullable=True)
    specifications_json: MappedColumn[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    source_type: MappedColumn[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type_enum"),
        nullable=False,
    )
    last_checked_at: MappedColumn[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    purchase_task: Mapped["PurchaseTask"] = relationship(
        "PurchaseTask",
        back_populates="product_candidates",
    )

    def __repr__(self) -> str:
        return (
            f"<ProductCandidate id={self.id!r} title={self.title!r} "
            f"provider={self.provider!r} source_type={self.source_type!r}>"
        )
