"""SQLAlchemy declarative base and shared mixins for Family OS models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, mapped_column, MappedColumn


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""
    pass


class UUIDMixin:
    """Mixin that provides a UUID primary key stored as a plain string (compatible with SQLite)."""

    id: MappedColumn[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )


class TimestampMixin:
    """Mixin providing created_at / updated_at timestamp columns."""

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
