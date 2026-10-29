"""Authentication API endpoints."""
from __future__ import annotations

from typing import Annotated, Any, Dict
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_correlation_id, get_current_user_id
from app.db.session import get_db
from app.schemas.auth import BootstrapRequest, LoginRequest, RefreshRequest, TokenResponse, UserInfo
from app.services.auth_service import AuthService

router = APIRouter()
_auth_service = AuthService()


@router.post("/bootstrap", response_model=TokenResponse)
async def bootstrap(
    req: BootstrapRequest,
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """One-time initialization of the first family and administrator."""
    result = await _auth_service.bootstrap(
        db=db,
        bootstrap_token=req.bootstrap_token,
        email=req.email,
        password=req.password,
        display_name=req.display_name,
        family_name=req.family_name,
        correlation_id=correlation_id,
    )
    return result


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """Authenticate and obtain JWT access + refresh tokens."""
    return await _auth_service.login(
        db=db,
        email=req.email,
        password=req.password,
        correlation_id=correlation_id,
    )


@router.post("/refresh")
async def refresh_token(
    req: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Obtain a new access token using a valid refresh token."""
    return await _auth_service.refresh(db=db, refresh_token=req.refresh_token)


@router.post("/logout")
async def logout():
    """Stateless logout acknowledgement."""
    return {"status": "ok", "message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo)
async def get_me(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details of the currently authenticated user."""
    return await _auth_service.get_current_user_info(db=db, user_id=user_id)
