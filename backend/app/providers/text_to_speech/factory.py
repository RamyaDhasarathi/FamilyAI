"""Factory for text-to-speech providers."""
from __future__ import annotations

from app.core.config import get_settings
from app.providers.text_to_speech.base import BaseTTSProvider
from app.providers.text_to_speech.disabled import DisabledTTSProvider

_tts_provider: BaseTTSProvider | None = None


def get_tts_provider() -> BaseTTSProvider:
    global _tts_provider
    if _tts_provider is None:
        # Default to disabled unless another provider is configured
        _tts_provider = DisabledTTSProvider()
    return _tts_provider
