"""MobileUseInstruction model for Family OS."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, MappedColumn, relationship

from app.db.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.purchase import PurchaseTask
    from app.db.models.approval import ApprovalRequest


class InstructionStatus(str, enum.Enum):
    """Lifecycle status of a mobile-use instruction."""

    CREATED = "CREATED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class MobileUseInstruction(UUIDMixin, Base):
    """An instruction issued by an agent to perform a mobile UI action on behalf of a user."""

    __tablename__ = "mobile_use_instructions"

    __table_args__ = (
        Index("ix_mobile_use_instructions_idempotency_key", "idempotency_key", unique=True),
    )

    family_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_task_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("purchase_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_agent: MappedColumn[str] = mapped_column(String(255), nullable=False)
    action_type: MappedColumn[str] = mapped_column(String(255), nullable=False)
    target_type: MappedColumn[str] = mapped_column(String(255), nullable=False)
    target_reference: MappedColumn[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: MappedColumn[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    policy_decision_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )
    approval_request_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("approval_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: MappedColumn[InstructionStatus] = mapped_column(
        SAEnum(InstructionStatus, name="instruction_status_enum"),
        default=InstructionStatus.CREATED,
        nullable=False,
        index=True,
    )
    idempotency_key: MappedColumn[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
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
    purchase_task: Mapped["PurchaseTask"] = relationship(
        "PurchaseTask",
        back_populates="mobile_use_instructions",
    )
    approval_request: Mapped[Optional["ApprovalRequest"]] = relationship(
        "ApprovalRequest",
        back_populates="mobile_use_instructions",
    )

    def __repr__(self) -> str:
        return (
            f"<MobileUseInstruction id={self.id!r} action_type={self.action_type!r} "
            f"status={self.status!r} idempotency_key={self.idempotency_key!r}>"
        )
