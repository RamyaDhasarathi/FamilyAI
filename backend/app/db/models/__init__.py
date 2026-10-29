"""Exports all ORM model classes so Alembic can detect them via metadata."""
from app.db.models.user import User
from app.db.models.family import (
    Family,
    FamilyMembership,
    FamilyRole,
    MembershipStatus,
    PermissionEffect,
    PermissionGrant,
)
from app.db.models.conversation import (
    AgentType,
    ContentType,
    Conversation,
    Message,
    SenderType,
)
from app.db.models.purchase import (
    ApprovalState,
    ExecutionState,
    ProductCandidate,
    PurchaseTask,
    PurchaseTaskStatus,
    SourceType,
)
from app.db.models.approval import ApprovalRequest, ApprovalStatus
from app.db.models.mobile_use import InstructionStatus, MobileUseInstruction
from app.db.models.audit import AuditEvent

__all__ = [
    # User
    "User",
    # Family
    "Family",
    "FamilyMembership",
    "FamilyRole",
    "MembershipStatus",
    "PermissionEffect",
    "PermissionGrant",
    # Conversation
    "AgentType",
    "ContentType",
    "Conversation",
    "Message",
    "SenderType",
    # Purchase
    "ApprovalState",
    "ExecutionState",
    "ProductCandidate",
    "PurchaseTask",
    "PurchaseTaskStatus",
    "SourceType",
    # Approval
    "ApprovalRequest",
    "ApprovalStatus",
    # Mobile use
    "InstructionStatus",
    "MobileUseInstruction",
    # Audit
    "AuditEvent",
]
