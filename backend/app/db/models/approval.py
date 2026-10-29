"""ApprovalRequest model for Family OS."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, MappedColumn, relationship

from app.db.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.purchase import PurchaseTask
    from app.db.models.mobile_use import MobileUseInstruction


class ApprovalStatus(str, enum.Enum):
    """Lifecycle status of an approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ApprovalRequest(UUIDMixin, Base):
    """A request for a family admin/adult to approve a pending action."""

    __tablename__ = "approval_requests"

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
    requested_by_membership_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("family_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approver_membership_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("family_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approval_type: MappedColumn[str] = mapped_column(String(255), nullable=False)
    status: MappedColumn[ApprovalStatus] = mapped_column(
        SAEnum(ApprovalStatus, name="approval_status_enum"),
        default=ApprovalStatus.PENDING,
        nullable=False,
        index=True,
    )
    request_payload_json: MappedColumn[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    decision_reason: MappedColumn[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    decided_at: MappedColumn[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: MappedColumn[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    purchase_task: Mapped["PurchaseTask"] = relationship(
        "PurchaseTask",
        back_populates="approval_requests",
    )
    mobile_use_instructions: Mapped[list["MobileUseInstruction"]] = relationship(
        "MobileUseInstruction",
        back_populates="approval_request",
    )

    def __repr__(self) -> str:
        return (
            f"<ApprovalRequest id={self.id!r} purchase_task_id={self.purchase_task_id!r} "
            f"status={self.status!r}>"
        )
