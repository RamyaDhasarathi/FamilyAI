"""Disabled / unavailable speech-to-text provider."""
from __future__ import annotations

from app.core.exceptions import ProviderUnavailable
from app.providers.speech_to_text.base import BaseSTTProvider, TranscriptionResult


class DisabledSTTProvider(BaseSTTProvider):
    """Provider indicating STT is not configured/disabled."""

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> TranscriptionResult:
        raise ProviderUnavailable("Speech-to-text")

    async def is_available(self) -> bool:
        return False

    @property
    def provider_name(self) -> str:
        return "disabled"
