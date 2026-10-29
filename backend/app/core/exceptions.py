"""Structured application exceptions and error codes."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error with a stable error code."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


# ── Auth ──────────────────────────────────────────────────────────────────────
class AuthenticationRequired(AppError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__("AUTHENTICATION_REQUIRED", message, 401)


class AccountInactive(AppError):
    def __init__(self):
        super().__init__("ACCOUNT_INACTIVE", "Account is inactive", 403)


class FamilyMembershipRequired(AppError):
    def __init__(self):
        super().__init__(
            "FAMILY_MEMBERSHIP_REQUIRED",
            "Active family membership required",
            403,
        )


class PermissionDenied(AppError):
    def __init__(self, reason: str = "Permission denied"):
        super().__init__("PERMISSION_DENIED", reason, 403)


class ApprovalRequired(AppError):
    def __init__(self, approval_id: Optional[str] = None):
        super().__init__(
            "APPROVAL_REQUIRED",
            "This action requires approval",
            403,
            {"approval_id": approval_id},
        )


class ApprovalExpired(AppError):
    def __init__(self):
        super().__init__("APPROVAL_EXPIRED", "Approval has expired", 403)


class PolicyChanged(AppError):
    def __init__(self):
        super().__init__(
            "POLICY_CHANGED",
            "Policy changed since approval was granted; re-authorization required",
            403,
        )


# ── Task State ────────────────────────────────────────────────────────────────
class InvalidTaskState(AppError):
    def __init__(self, current: str, expected: str):
        super().__init__(
            "INVALID_TASK_STATE",
            f"Task is in state '{current}', expected '{expected}'",
            409,
        )


# ── Instruction ───────────────────────────────────────────────────────────────
class InvalidInstruction(AppError):
    def __init__(self, reason: str = "Invalid instruction"):
        super().__init__("INVALID_INSTRUCTION", reason, 422)


class InstructionExpired(AppError):
    def __init__(self):
        super().__init__("INSTRUCTION_EXPIRED", "Instruction has expired", 410)


class DuplicateExecution(AppError):
    def __init__(self, idempotency_key: str):
        super().__init__(
            "DUPLICATE_EXECUTION",
            "Duplicate execution request detected",
            409,
            {"idempotency_key": idempotency_key},
        )


class OutcomeUnknown(AppError):
    def __init__(self):
        super().__init__(
            "OUTCOME_UNKNOWN",
            "Execution outcome is unknown; reconcile before retrying",
            500,
        )


# ── Providers ─────────────────────────────────────────────────────────────────
class ProviderUnavailable(AppError):
    def __init__(self, provider: str):
        super().__init__(
            f"{provider.upper()}_PROVIDER_UNAVAILABLE",
            f"{provider} provider is unavailable",
            503,
        )


class ValidationError(AppError):
    def __init__(self, reason: str):
        super().__init__("VALIDATION_ERROR", reason, 422)


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str = ""):
        super().__init__(
            "NOT_FOUND",
            f"{resource} not found" + (f": {resource_id}" if resource_id else ""),
            404,
        )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError to a structured JSON response."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    body: Dict[str, Any] = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "correlation_id": correlation_id,
        }
    }
    if exc.details:
        body["error"]["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=body)


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Generic fallback error handler - does not expose internals."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
                "correlation_id": correlation_id,
            }
        },
    )
