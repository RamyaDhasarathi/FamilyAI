"""Conversation and Message models for Family OS."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, MappedColumn, relationship

from app.db.base import Base, UUIDMixin


class AgentType(str, enum.Enum):
    """The kind of AI agent that owns a conversation."""

    PURCHASE = "PURCHASE"
    TRAVEL = "TRAVEL"


class SenderType(str, enum.Enum):
    """Who (or what) sent a message."""

    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class ContentType(str, enum.Enum):
    """The encoding or semantic type of message content."""

    TEXT = "TEXT"
    TRANSCRIPTION = "TRANSCRIPTION"
    AUDIO_REFERENCE = "AUDIO_REFERENCE"
    STRUCTURED = "STRUCTURED"


class Conversation(UUIDMixin, Base):
    """A threaded conversation between a family member and a Family OS agent."""

    __tablename__ = "conversations"

    family_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_membership_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("family_memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_type: MappedColumn[AgentType] = mapped_column(
        SAEnum(AgentType, name="agent_type_enum"),
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
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation id={self.id!r} family_id={self.family_id!r} "
            f"agent_type={self.agent_type!r}>"
        )


class Message(UUIDMixin, Base):
    """A single message within a Conversation."""

    __tablename__ = "messages"

    conversation_id: MappedColumn[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_type: MappedColumn[SenderType] = mapped_column(
        SAEnum(SenderType, name="sender_type_enum"),
        nullable=False,
    )
    content: MappedColumn[str] = mapped_column(Text, nullable=False)
    content_type: MappedColumn[ContentType] = mapped_column(
        SAEnum(ContentType, name="content_type_enum"),
        default=ContentType.TEXT,
        nullable=False,
    )
    metadata_json: MappedColumn[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return (
            f"<Message id={self.id!r} conversation_id={self.conversation_id!r} "
            f"sender_type={self.sender_type!r} content_type={self.content_type!r}>"
        )
