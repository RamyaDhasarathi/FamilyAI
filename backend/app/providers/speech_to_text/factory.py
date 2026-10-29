"""Factory for speech-to-text providers."""
from __future__ import annotations

from app.core.config import get_settings
from app.providers.speech_to_text.base import BaseSTTProvider
from app.providers.speech_to_text.disabled import DisabledSTTProvider

_stt_provider: BaseSTTProvider | None = None


def get_stt_provider() -> BaseSTTProvider:
    global _stt_provider
    if _stt_provider is None:
        settings = get_settings()
        if settings.STT_PROVIDER == "whisper_local":
            try:
                # If whisper is installed locally, we could load it, otherwise fallback
                from app.providers.speech_to_text.whisper_local import WhisperLocalProvider
                _stt_provider = WhisperLocalProvider()
            except ImportError:
                _stt_provider = DisabledSTTProvider()
        else:
            _stt_provider = DisabledSTTProvider()
    return _stt_provider
