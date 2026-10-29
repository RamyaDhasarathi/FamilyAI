"""Deterministic mock LLM provider for testing and development."""
from __future__ import annotations

import json
from typing import Any, List

from app.providers.llm.base import BaseLLMProvider, ChatMessage, LLMResponse

# ---------------------------------------------------------------------------
# Canned structured responses
# ---------------------------------------------------------------------------

_MOUSE_INTENT = {
    "response_type": "recommendation",
    "reply_text": (
        "I found several wireless mice in our catalogue. "
        "I'll compare them by price, specs, and availability."
    ),
    "purchase_intent": {
        "category": "MOUSE",
        "item": "wireless mouse",
        "budget_amount": None,
        "currency": "INR",
        "brand_preference": [],
        "required_specs": {"Connection": "USB nano receiver"},
        "quantity": 1,
        "missing_info": [],
    },
    "ready_to_search": True,
    "clarification_question": None,
}

_LAPTOP_INTENT = {
    "response_type": "recommendation",
    "reply_text": (
        "Great! I'll search for laptops that match your needs. "
        "Let me find the best options available."
    ),
    "purchase_intent": {
        "category": "LAPTOP",
        "item": "laptop",
        "budget_amount": None,
        "currency": "INR",
        "brand_preference": [],
        "required_specs": {},
        "quantity": 1,
        "missing_info": [],
    },
    "ready_to_search": True,
    "clarification_question": None,
}

_WASHING_MACHINE_INTENT = {
    "response_type": "clarification",
    "reply_text": (
        "I'd love to help you find a washing machine! "
        "Could you let me know your preferred type — front load or top load — "
        "and your budget?"
    ),
    "purchase_intent": {
        "category": "WASHING_MACHINE",
        "item": "washing machine",
        "budget_amount": None,
        "currency": "INR",
        "brand_preference": [],
        "required_specs": {},
        "quantity": 1,
        "missing_info": ["load_type", "budget_amount"],
    },
    "ready_to_search": False,
    "clarification_question": (
        "What type of washing machine do you prefer (front load / top load) "
        "and what is your budget?"
    ),
}

_CLARIFICATION_RESPONSE = {
    "response_type": "clarification",
    "reply_text": (
        "I want to make sure I find exactly the right product for you. "
        "Could you provide a bit more detail about what you're looking for?"
    ),
    "purchase_intent": {
        "category": "",
        "item": "",
        "budget_amount": None,
        "currency": "INR",
        "brand_preference": [],
        "required_specs": {},
        "quantity": 1,
        "missing_info": ["category", "item"],
    },
    "ready_to_search": False,
    "clarification_question": (
        "Could you tell me more about what you'd like to buy? "
        "For example: the type of product, your budget, and any brand preferences?"
    ),
}

_GENERIC_RESPONSE = {
    "response_type": "answer",
    "reply_text": (
        "I'm here to help you find and purchase products for your family. "
        "Just tell me what you'd like to buy!"
    ),
    "purchase_intent": {
        "category": "",
        "item": "",
        "budget_amount": None,
        "currency": "INR",
        "brand_preference": [],
        "required_specs": {},
        "quantity": 1,
        "missing_info": ["category", "item"],
    },
    "ready_to_search": False,
    "clarification_question": None,
}


def _pick_response(last_user_message: str) -> dict:
    """Return the canned response dict that best matches the user message."""
    import re
    msg_lower = last_user_message.lower()
    if "mouse" in msg_lower:
        base = json.loads(json.dumps(_MOUSE_INTENT))
    elif "laptop" in msg_lower:
        base = json.loads(json.dumps(_LAPTOP_INTENT))
    elif "washing machine" in msg_lower or "washer" in msg_lower:
        base = json.loads(json.dumps(_WASHING_MACHINE_INTENT))
    elif "clarif" in msg_lower or "what do you" in msg_lower or "?" in msg_lower:
        base = json.loads(json.dumps(_CLARIFICATION_RESPONSE))
    else:
        base = json.loads(json.dumps(_GENERIC_RESPONSE))

    # Extract brand preference if mentioned
    brands = []
    for b in ["Logitech", "HP", "Dell", "Lenovo", "Samsung", "LG", "Whirlpool", "Wildcraft", "AmazonBasics"]:
        if b.lower() in msg_lower:
            brands.append(b)
    if brands and "purchase_intent" in base:
        base["purchase_intent"]["brand_preference"] = brands

    # Extract budget if mentioned
    match = re.search(r"(?:under|below|for|budget)?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*)", msg_lower)
    if match and "purchase_intent" in base:
        try:
            amt = float(match.group(1).replace(",", ""))
            base["purchase_intent"]["budget_amount"] = amt
        except ValueError:
            pass

    return base


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider — never calls a real model.

    Responses are selected by keyword matching on the last *user* message so
    that test suites and demo environments get stable, predictable output.
    """

    @property
    def provider_name(self) -> str:  # noqa: D102
        return "mock"

    async def is_available(self) -> bool:  # noqa: D102
        return True

    async def chat(self, messages: List[ChatMessage], **kwargs: Any) -> LLMResponse:
        """Return a deterministic JSON response without calling any real LLM."""
        # Find the last user message to key on.
        last_user_content = ""
        for msg in reversed(messages):
            if msg.role == "user":
                last_user_content = msg.content
                break

        response_dict = _pick_response(last_user_content)
        return LLMResponse(
            content=json.dumps(response_dict),
            is_mock=True,
            provider=self.provider_name,
            model="mock-v1",
            usage={},
        )
