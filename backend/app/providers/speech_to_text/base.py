"""Abstract base for speech-to-text providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class TranscriptionResult(BaseModel):
    text: str
    is_available: bool = True
    provider: str
    confidence: Optional[float] = None
    language: Optional[str] = "en"


class BaseSTTProvider(ABC):
    """Abstract interface for speech transcription."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> TranscriptionResult:
        """Transcribe audio bytes to text."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True if this provider is currently available."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...
