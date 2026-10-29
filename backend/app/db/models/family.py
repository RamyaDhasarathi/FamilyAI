"""Family, FamilyMembership, and PermissionGrant models for Family OS."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, MappedColumn, relationship

from app.db.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class FamilyRole(str, enum.Enum):
    """Roles a member can hold within a family."""

    ADMIN = "ADMIN"
    ADULT_MEMBER = "ADULT_MEMBER"
    CHILD_MEMBER = "CHILD_MEMBER"


class MembershipStatus(str, enum.Enum):
    """Lifecycle status of a family membership."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class PermissionEffect(str, enum.Enum):
    """Whether a permission grant allows or denies the action."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class Family(UUIDMixin, Base):
    """A family unit that groups users and scopes all operations."""

    __tablename__ = "families"

    name: MappedColumn[str] = mapped_column(String(255), nullable=False)
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
        back_populates="family",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Family id={self.id!r} name={self.name!r}>"


class FamilyMembership(UUIDMixin, Base):
    """Associates a User with a Family, carrying role and status information."""

    __tablename__ = "family_memberships"

    __table_args__ = (
        # Unique constraint at DB level for the (user_id, family_id) pair so that
        # application-level enforcement (only one ACTIVE membership per pair) is
        # supported. A partial unique index (WHERE status=ACTIVE) is the ideal
        # approach but SQLite does not reliably support it via SQLAlchemy's
        # server_default, so we enforce uniqueness in the application layer and
        # add a composite index here for lookup performance.
        Index("ix_family_memberships_user_family", "user_id", "family_id"),
        UniqueConstraint("user_id", "family_id", name="uq_membership_user_family"),
    )

    family_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    family_role: MappedColumn[FamilyRole] = mapped_column(
        SAEnum(FamilyRole, name="family_role_enum"),
        nullable=False,
    )
    membership_status: MappedColumn[MembershipStatus] = mapped_column(
        SAEnum(MembershipStatus, name="membership_status_enum"),
        default=MembershipStatus.ACTIVE,
        nullable=False,
    )
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    family: Mapped["Family"] = relationship("Family", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="memberships")
    permission_grants: Mapped[list["PermissionGrant"]] = relationship(
        "PermissionGrant",
        foreign_keys="PermissionGrant.subject_membership_id",
        back_populates="subject_membership",
        cascade="all, delete-orphan",
    )
    created_permission_grants: Mapped[list["PermissionGrant"]] = relationship(
        "PermissionGrant",
        foreign_keys="PermissionGrant.created_by_membership_id",
        back_populates="created_by_membership",
    )

    def __repr__(self) -> str:
        return (
            f"<FamilyMembership id={self.id!r} user_id={self.user_id!r} "
            f"family_id={self.family_id!r} role={self.family_role!r} "
            f"status={self.membership_status!r}>"
        )


class PermissionGrant(UUIDMixin, Base):
    """Grants or denies a specific action on a resource to a family member."""

    __tablename__ = "permission_grants"

    __table_args__ = (
        Index("ix_permission_grants_resource", "resource"),
        Index("ix_permission_grants_action", "action"),
    )

    family_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_membership_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("family_memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource: MappedColumn[str] = mapped_column(String(255), nullable=False)
    action: MappedColumn[str] = mapped_column(String(255), nullable=False)
    effect: MappedColumn[PermissionEffect] = mapped_column(
        SAEnum(PermissionEffect, name="permission_effect_enum"),
        nullable=False,
    )
    approval_required: MappedColumn[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    constraints_json: MappedColumn[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    created_by_membership_id: MappedColumn[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("family_memberships.id", ondelete="SET NULL"),
        nullable=True,
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
    subject_membership: Mapped["FamilyMembership"] = relationship(
        "FamilyMembership",
        foreign_keys=[subject_membership_id],
        back_populates="permission_grants",
    )
    created_by_membership: Mapped[Optional["FamilyMembership"]] = relationship(
        "FamilyMembership",
        foreign_keys=[created_by_membership_id],
        back_populates="created_permission_grants",
    )

    def __repr__(self) -> str:
        return (
            f"<PermissionGrant id={self.id!r} resource={self.resource!r} "
            f"action={self.action!r} effect={self.effect!r}>"
        )
