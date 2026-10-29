"""AuditEvent model for Family OS."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import mapped_column, MappedColumn

from app.db.base import Base, UUIDMixin


class AuditEvent(UUIDMixin, Base):
    """Immutable audit log entry capturing every significant system action."""

    __tablename__ = "audit_events"

    __table_args__ = (
        Index("ix_audit_events_action", "action"),
        Index("ix_audit_events_correlation_id", "correlation_id"),
    )

    family_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    actor_type: MappedColumn[str] = mapped_column(String(255), nullable=False)
    actor_id: MappedColumn[Optional[str]] = mapped_column(String(36), nullable=True)
    action: MappedColumn[str] = mapped_column(String(255), nullable=False)
    resource_type: MappedColumn[str] = mapped_column(String(255), nullable=False)
    resource_id: MappedColumn[Optional[str]] = mapped_column(String(36), nullable=True)
    decision: MappedColumn[Optional[str]] = mapped_column(String(255), nullable=True)
    reason_code: MappedColumn[Optional[str]] = mapped_column(String(255), nullable=True)
    correlation_id: MappedColumn[str] = mapped_column(String(255), nullable=False)
    metadata_json: MappedColumn[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id!r} action={self.action!r} "
            f"actor_type={self.actor_type!r} resource_type={self.resource_type!r}>"
        )
