"""FastAPI dependencies for authentication and family context."""
from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationRequired, AccountInactive, FamilyMembershipRequired
from app.core.security import JWTError, decode_token
from app.db.session import get_db

security = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> str:
    """Extract and validate the JWT, return user_id (sub claim)."""
    if credentials is None:
        raise AuthenticationRequired()
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise AuthenticationRequired("Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationRequired("Token missing subject")
        return user_id
    except JWTError as exc:
        raise AuthenticationRequired(f"Invalid token: {exc}") from exc


async def get_current_user(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Load the User record for the authenticated user_id."""
    from app.db.models.user import User
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationRequired("User not found")
    if not user.is_active:
        raise AccountInactive()
    return user


async def get_current_membership(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Load the active FamilyMembership for the current user."""
    from app.db.models.family import FamilyMembership, MembershipStatus
    from sqlalchemy import select

    result = await db.execute(
        select(FamilyMembership).where(
            FamilyMembership.user_id == user.id,
            FamilyMembership.membership_status == MembershipStatus.ACTIVE,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise FamilyMembershipRequired()
    return membership


async def get_correlation_id(
    x_correlation_id: Optional[str] = Header(None),
) -> str:
    import uuid
    return x_correlation_id or str(uuid.uuid4())
