"""User model for Family OS."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import mapped_column, Mapped, MappedColumn, relationship

if TYPE_CHECKING:
    from app.db.models.family import FamilyMembership

from app.db.base import Base, UUIDMixin


class User(UUIDMixin, Base):
    """Represents an authenticated human user in the system."""

    __tablename__ = "users"

    email: MappedColumn[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    display_name: MappedColumn[str] = mapped_column(
        String(255),
        nullable=False,
    )
    password_hash: MappedColumn[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_active: MappedColumn[bool] = mapped_column(
        Boolean,
        default=True,
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
    memberships: Mapped[list["FamilyMembership"]] = relationship(
        "FamilyMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r} display_name={self.display_name!r}>"
