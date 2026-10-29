"""Disabled text-to-speech provider."""
from __future__ import annotations

from app.core.exceptions import ProviderUnavailable
from app.providers.text_to_speech.base import BaseTTSProvider, SynthesisResult


class DisabledTTSProvider(BaseTTSProvider):
    async def synthesize(self, text: str) -> SynthesisResult:
        raise ProviderUnavailable("Text-to-speech")

    async def is_available(self) -> bool:
        return False

    @property
    def provider_name(self) -> str:
        return "disabled"
