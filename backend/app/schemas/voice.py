"""Voice (STT / TTS) Pydantic schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class TranscribeResponse(BaseModel):
    """Result of a speech-to-text transcription request."""

    text: Optional[str]
    is_available: bool
    message: Optional[str] = None


class SynthesizeRequest(BaseModel):
    """Payload to synthesise speech from text."""

    text: str


class SynthesizeResponse(BaseModel):
    """Result of a text-to-speech synthesis request."""

    audio_url: Optional[str]
    is_available: bool
    message: Optional[str] = None
