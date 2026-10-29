"""Authentication and family onboarding service."""
from __future__ import annotations

import uuid
from typing import Any, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    AccountInactive,
    AuthenticationRequired,
    FamilyMembershipRequired,
    PermissionDenied,
    ValidationError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models.family import Family, FamilyMembership, FamilyRole, MembershipStatus
from app.db.models.user import User
from app.policies.defaults import create_default_grants, create_member_default_grants
from app.services.audit_service import AuditService

_auditor = AuditService()


class AuthService:
    """Handles bootstrap, login, token refresh, and user onboarding."""

    async def bootstrap(
        self,
        db: AsyncSession,
        bootstrap_token: str,
        email: str,
        password: str,
        display_name: str,
        family_name: str,
        correlation_id: str = "bootstrap",
    ) -> Dict[str, Any]:
        """One-time bootstrap endpoint to initialize the first family and admin."""
        settings = get_settings()

        # Validate token
        if not bootstrap_token or bootstrap_token != settings.BOOTSTRAP_TOKEN:
            raise PermissionDenied("Invalid bootstrap token")

        # Check if any family already exists
        existing_family = await db.execute(select(Family))
        if existing_family.scalars().first() is not None:
            raise PermissionDenied("Bootstrap has already been completed")

        # Check if user already exists
        existing_user = await db.execute(select(User).where(User.email == email))
        if existing_user.scalars().first() is not None:
            raise ValidationError("A user with this email already exists")

        # Create Family
        family_id = str(uuid.uuid4())
        family = Family(id=family_id, name=family_name)
        db.add(family)

        # Create Admin User
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)

        # Create Admin Membership
        membership_id = str(uuid.uuid4())
        membership = FamilyMembership(
            id=membership_id,
            family_id=family_id,
            user_id=user_id,
            family_role=FamilyRole.ADMIN,
            membership_status=MembershipStatus.ACTIVE,
        )
        db.add(membership)
        await db.flush()

        # Create default grants for admin
        await create_default_grants(db, family_id, membership_id)

        # Log audit
        await _auditor.log(
            db=db,
            family_id=family_id,
            actor_type="SYSTEM",
            actor_id=user_id,
            action="family.bootstrap",
            resource_type="family",
            resource_id=family_id,
            decision="ALLOW",
            reason_code="BOOTSTRAP_SUCCESS",
            correlation_id=correlation_id,
            metadata={"admin_email": email, "family_name": family_name},
        )
        await db.commit()

        # Generate tokens
        access_token = create_access_token(
            subject=user_id,
            extra_claims={"family_id": family_id, "membership_id": membership_id, "role": "ADMIN"},
        )
        refresh_token = create_refresh_token(subject=user_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user_id,
            "display_name": display_name,
            "family_id": family_id,
            "membership_id": membership_id,
            "family_role": "ADMIN",
            "family_name": family_name,
        }

    async def login(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        correlation_id: str = "login",
    ) -> Dict[str, Any]:
        """Authenticate user by email and password."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationRequired("Invalid email or password")

        if not user.is_active:
            raise AccountInactive()

        # Get active membership
        mem_result = await db.execute(
            select(FamilyMembership).where(
                FamilyMembership.user_id == user.id,
                FamilyMembership.membership_status == MembershipStatus.ACTIVE,
            )
        )
        membership = mem_result.scalar_one_or_none()
        if membership is None:
            raise FamilyMembershipRequired()

        # Get family name
        family_result = await db.execute(
            select(Family).where(Family.id == membership.family_id)
        )
        family = family_result.scalar_one_or_none()
        family_name = family.name if family else "Family OS"

        role_str = membership.family_role.value if hasattr(membership.family_role, "value") else str(membership.family_role)

        access_token = create_access_token(
            subject=user.id,
            extra_claims={
                "family_id": membership.family_id,
                "membership_id": membership.id,
                "role": role_str,
            },
        )
        refresh_token = create_refresh_token(subject=user.id)

        await _auditor.log(
            db=db,
            family_id=membership.family_id,
            actor_type="USER",
            actor_id=user.id,
            action="auth.login",
            resource_type="user",
            resource_id=user.id,
            decision="ALLOW",
            reason_code="LOGIN_SUCCESS",
            correlation_id=correlation_id,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
            "display_name": user.display_name,
            "family_id": membership.family_id,
            "membership_id": membership.id,
            "family_role": role_str,
            "family_name": family_name,
        }

    async def refresh(
        self,
        db: AsyncSession,
        refresh_token: str,
    ) -> Dict[str, Any]:
        """Issue a new access token using a valid refresh token."""
        try:
            payload = decode_token(refresh_token)
        except Exception as exc:
            raise AuthenticationRequired("Invalid or expired refresh token") from exc

        if payload.get("type") != "refresh":
            raise AuthenticationRequired("Token is not a refresh token")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationRequired("Invalid token claims")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise AuthenticationRequired("User inactive or not found")

        mem_result = await db.execute(
            select(FamilyMembership).where(
                FamilyMembership.user_id == user.id,
                FamilyMembership.membership_status == MembershipStatus.ACTIVE,
            )
        )
        membership = mem_result.scalar_one_or_none()
        if not membership:
            raise FamilyMembershipRequired()

        role_str = membership.family_role.value if hasattr(membership.family_role, "value") else str(membership.family_role)

        access_token = create_access_token(
            subject=user.id,
            extra_claims={
                "family_id": membership.family_id,
                "membership_id": membership.id,
                "role": role_str,
            },
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    async def get_current_user_info(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Dict[str, Any]:
        """Get profile and membership details for the authenticated user."""
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise AuthenticationRequired("User not found")

        mem_result = await db.execute(
            select(FamilyMembership).where(
                FamilyMembership.user_id == user.id,
                FamilyMembership.membership_status == MembershipStatus.ACTIVE,
            )
        )
        membership = mem_result.scalar_one_or_none()
        if not membership:
            raise FamilyMembershipRequired()

        family_result = await db.execute(
            select(Family).where(Family.id == membership.family_id)
        )
        family = family_result.scalar_one_or_none()

        role_str = membership.family_role.value if hasattr(membership.family_role, "value") else str(membership.family_role)

        return {
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "is_active": user.is_active,
            "family_id": membership.family_id,
            "membership_id": membership.id,
            "family_role": role_str,
            "family_name": family.name if family else "Family OS",
        }
