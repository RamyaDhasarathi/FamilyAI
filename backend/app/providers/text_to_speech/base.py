"""Abstract base for text-to-speech providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class SynthesisResult(BaseModel):
    audio_content: bytes
    media_type: str = "audio/mpeg"
    is_available: bool = True
    provider: str


class BaseTTSProvider(ABC):
    """Abstract interface for speech synthesis."""

    @abstractmethod
    async def synthesize(self, text: str) -> SynthesisResult:
        """Convert text to speech audio bytes."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True if TTS is available."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...
