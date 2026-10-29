"""Shared Pydantic response schemas for the Family OS API."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response body."""

    code: str
    message: str
    correlation_id: str
    details: Optional[dict] = None


class SuccessResponse(BaseModel):
    """Standard success response body."""

    success: bool = True
    message: str = "OK"
    correlation_id: str
