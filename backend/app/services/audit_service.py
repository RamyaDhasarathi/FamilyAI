"""Audit event logging service for Family OS.

All methods are fire-and-forget safe: failures are written to stderr only and
never propagate to callers.  This ensures that audit log failures never block
the primary business operation.
"""
from __future__ import annotations

import json
import sys
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent


class AuditService:
    """Append-only audit event logger.

    Construct a single instance (module-level or via DI) and call :meth:`log`
    from anywhere that needs to record an authorization or business decision.
    """

    async def log(
        self,
        db: AsyncSession,
        family_id: str,
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str = "",
        decision: str = "",
        reason_code: str = "",
        correlation_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        """Persist an audit event to the database.

        This method **never raises**.  Any exception is caught, printed to
        stderr, and ``None`` is returned so that callers can proceed normally.

        Args:
            db: An active async SQLAlchemy session.
            family_id: UUID of the family context.
            actor_type: One of ``"USER"``, ``"AGENT"``, or ``"SYSTEM"``.
            actor_id: Identifier of the acting entity (user ID, agent name, etc.).
            action: The action that was attempted (e.g. ``"purchase.execute"``).
            resource_type: The resource category (e.g. ``"purchase.execution"``).
            resource_id: Optional specific resource UUID or identifier.
            decision: Policy decision outcome (e.g. ``"ALLOW"``, ``"DENY"``, ``"ASK"``).
            reason_code: Machine-readable reason code from the policy engine.
            correlation_id: Request correlation ID for cross-service tracing.
            metadata: Optional dict of extra contextual data to serialise as JSON.

        Returns:
            The persisted :class:`~app.db.models.audit.AuditEvent`, or ``None``
            if an error occurred.
        """
        try:
            event = AuditEvent(
                id=str(uuid.uuid4()),
                family_id=family_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id or "",
                decision=decision,
                reason_code=reason_code,
                correlation_id=correlation_id or str(uuid.uuid4()),
                metadata_json=json.dumps(metadata or {}),
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            await db.flush()  # assign DB-generated values without committing
            return event
        except Exception:  # noqa: BLE001
            print(
                f"[AuditService] Failed to persist audit event: "
                f"action={action!r} actor={actor_id!r} family={family_id!r}\n"
                f"{traceback.format_exc()}",
                file=sys.stderr,
            )
            return None
