"""Base agent abstraction for Family OS."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession


class BaseAgent(ABC):
    """Abstract base class for all conversational and execution agents."""

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """String identifier of the agent (e.g. 'PURCHASE', 'TRAVEL')."""
        ...

    @abstractmethod
    async def process_message(
        self,
        db: AsyncSession,
        conversation_id: str,
        user_message: str,
        task_id: Optional[str],
        membership,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """Process an incoming user message and return structured response."""
        ...
