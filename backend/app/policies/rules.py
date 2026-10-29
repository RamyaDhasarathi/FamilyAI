"""Resource/action constants and constraint validation for FGP policy engine."""
from __future__ import annotations

from typing import Tuple


class RA:
    """Resource-Action pairs used throughout the Family Governance Platform.

    Each class attribute is a ``(resource, action)`` tuple that can be passed
    directly to ``PolicyEngine.evaluate``.
    """

    AGENT_PURCHASE_USE: Tuple[str, str] = ("agent.purchase", "use")
    PURCHASE_TASK_CREATE: Tuple[str, str] = ("purchase.task", "create")
    PURCHASE_TASK_READ: Tuple[str, str] = ("purchase.task", "read")
    PURCHASE_TASK_UPDATE: Tuple[str, str] = ("purchase.task", "update")
    PURCHASE_CATALOGUE_SEARCH: Tuple[str, str] = ("purchase.catalogue", "search")
    PURCHASE_PRODUCT_SELECT: Tuple[str, str] = ("purchase.product", "select")
    PURCHASE_EXECUTION_PREPARE: Tuple[str, str] = ("purchase.execution", "prepare")
    PURCHASE_EXECUTION_EXECUTE: Tuple[str, str] = ("purchase.execution", "execute")
    PURCHASE_EXECUTION_SIMULATE: Tuple[str, str] = ("purchase.execution", "simulate")
    FAMILY_MEMBERS_READ: Tuple[str, str] = ("family.members", "read")
    FAMILY_PERMISSIONS_READ: Tuple[str, str] = ("family.permissions", "read")
    FAMILY_PERMISSIONS_UPDATE: Tuple[str, str] = ("family.permissions", "update")
    APPROVAL_REQUEST_CREATE: Tuple[str, str] = ("approval.request", "create")
    APPROVAL_REQUEST_READ: Tuple[str, str] = ("approval.request", "read")
    APPROVAL_REQUEST_DECIDE: Tuple[str, str] = ("approval.request", "decide")
    MOBILE_USE_INSTRUCTION_CREATE: Tuple[str, str] = ("mobile_use.instruction", "create")
    MOBILE_USE_INSTRUCTION_READ: Tuple[str, str] = ("mobile_use.instruction", "read")
    MOBILE_USE_INSTRUCTION_EXECUTE: Tuple[str, str] = ("mobile_use.instruction", "execute")
    VOICE_TRANSCRIPTION_USE: Tuple[str, str] = ("voice.transcription", "use")
    VOICE_SPEECH_GENERATE: Tuple[str, str] = ("voice.speech", "generate")

    @classmethod
    def all(cls) -> list[Tuple[str, str]]:
        """Return all defined resource-action tuples."""
        return [
            v
            for k, v in vars(cls).items()
            if not k.startswith("_") and isinstance(v, tuple)
        ]


# ── Known constraint keys per action ─────────────────────────────────────────

# For execution actions, only these constraint keys are considered safe.
# Any *unknown* key in the constraints dict causes validation to fail.
_EXECUTION_ALLOWED_CONSTRAINT_KEYS: frozenset[str] = frozenset(
    {
        "max_spend",
        "max_spend_pence",
        "currency",
        "max_items",
        "allowed_categories",
        "blocked_categories",
        "require_simulation_first",
        "requires_user_confirmation",
        "requires_admin_approval",
        "require_approval",
        "own_purchases_only",
        "mobile_use_allowed",
        "allow_simulation",
        "expires_at",
        "allowed_merchants",
        "blocked_merchants",
        "allowed_payment_methods",
        "allowed_apps",
        "target_app",
        "qwen_mode",
        "max_steps",
    }
)

# Actions that are treated as security-sensitive for execution purposes.
_EXECUTION_SENSITIVE_ACTIONS: frozenset[str] = frozenset(
    {
        "execute",
        "prepare",
        "create",
        "update",
        "decide",
    }
)


def validate_constraints(constraints: dict, action: str) -> bool:
    """Return ``True`` if *constraints* are valid for *action*, ``False`` otherwise.

    For security-sensitive execution actions any constraint key that is not in
    the known-safe allow-list will cause this function to return ``False``.
    For read/search/simulate/use/generate actions all constraints are accepted
    (they are informational only and do not gate safety decisions).

    Args:
        constraints: The constraints dictionary from a :class:`PermissionGrant`.
        action: The action string (e.g. ``"execute"``, ``"read"``).

    Returns:
        ``True`` if the constraints are acceptable, ``False`` if they contain
        unknown security-sensitive keys for a sensitive action.
    """
    if not isinstance(constraints, dict):
        return False

    if action in _EXECUTION_SENSITIVE_ACTIONS:
        unknown_keys = set(constraints.keys()) - _EXECUTION_ALLOWED_CONSTRAINT_KEYS
        if unknown_keys:
            return False

    return True
