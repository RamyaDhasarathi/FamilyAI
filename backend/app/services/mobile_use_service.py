"""Mobile Use instruction management service."""
from __future__ import annotations

from typing import List, Optional
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDenied
from app.db.models.mobile_use import InstructionStatus, MobileUseInstruction
from app.policies.engine import PolicyEngine
from app.policies.rules import RA
from app.services.audit_service import AuditService

_engine = PolicyEngine()
_auditor = AuditService()


class MobileUseService:
    """Manages mobile execution instructions."""

    async def get_instruction(
        self,
        db: AsyncSession,
        instruction_id: str,
        membership_id: str,
        family_id: str,
    ) -> MobileUseInstruction:
        """Fetch an instruction by ID, verifying family scope."""
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=membership_id,
            family_id=family_id,
            resource=RA.MOBILE_USE_INSTRUCTION_READ[0],
            action=RA.MOBILE_USE_INSTRUCTION_READ[1],
            purpose="Read mobile use instruction",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        stmt = select(MobileUseInstruction).where(
            and_(
                MobileUseInstruction.id == instruction_id,
                MobileUseInstruction.family_id == family_id,
            )
        )
        result = await db.execute(stmt)
        instruction = result.scalar_one_or_none()
        if not instruction:
            raise NotFoundError("MobileUseInstruction", instruction_id)
        return instruction

    async def list_instructions(
        self,
        db: AsyncSession,
        membership_id: str,
        family_id: str,
    ) -> List[MobileUseInstruction]:
        """List instructions in the family."""
        stmt = (
            select(MobileUseInstruction)
            .where(MobileUseInstruction.family_id == family_id)
            .order_by(MobileUseInstruction.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def cancel_instruction(
        self,
        db: AsyncSession,
        instruction_id: str,
        membership_id: str,
        family_id: str,
    ) -> MobileUseInstruction:
        """Cancel an instruction."""
        instruction = await self.get_instruction(db, instruction_id, membership_id, family_id)
        instruction.status = InstructionStatus.CANCELLED
        await db.flush()
        return instruction
