"""Abstract LLM provider interface for Family OS."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A single turn in a chat conversation."""

    role: str  # 'system', 'user', 'assistant'
    content: str


class LLMResponse(BaseModel):
    """Normalised response returned by any LLM provider."""

    content: str
    is_mock: bool = False
    provider: str = ""
    model: str = ""
    usage: Dict[str, Any] = {}


class BaseLLMProvider(ABC):
    """Abstract base class that every LLM provider must implement."""

    @abstractmethod
    async def chat(self, messages: List[ChatMessage], **kwargs: Any) -> LLMResponse:
        """Send a list of chat messages and return the model reply.

        Args:
            messages: Ordered list of :class:`ChatMessage` objects representing
                the conversation so far.
            **kwargs: Provider-specific overrides (e.g. temperature, max_tokens).

        Returns:
            :class:`LLMResponse` with the model's reply and metadata.
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """Return ``True`` if the provider is reachable and ready."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of this provider (e.g. ``'mock'``, ``'ollama'``)."""
