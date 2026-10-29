"""Voice transcription and synthesis endpoints."""
from __future__ import annotations

import os
from typing import Optional
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_membership
from app.core.exceptions import PermissionDenied, ValidationError
from app.db.models.family import FamilyMembership
from app.db.session import get_db
from app.policies.engine import PolicyEngine
from app.policies.rules import RA
from app.providers.speech_to_text.factory import get_stt_provider
from app.providers.text_to_speech.factory import get_tts_provider
from app.schemas.voice import SynthesizeRequest, SynthesizeResponse, TranscribeResponse

router = APIRouter()
_engine = PolicyEngine()

ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/mpeg",
    "audio/webm",
    "audio/ogg",
    "application/octet-stream",
}


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Transcribe voice input from mobile client."""
    # FGP check
    decision = await _engine.evaluate(
        db=db,
        principal_membership_id=membership.id,
        family_id=membership.family_id,
        resource=RA.VOICE_TRANSCRIPTION_USE[0],
        action=RA.VOICE_TRANSCRIPTION_USE[1],
        purpose="Transcribe voice input",
    )
    if decision.effect == "DENY":
        raise PermissionDenied(decision.human_readable_reason)

    settings = get_settings()
    max_bytes = settings.MAX_AUDIO_UPLOAD_MB * 1024 * 1024

    # Validate content type
    if file.content_type and file.content_type.lower() not in ALLOWED_AUDIO_TYPES:
        raise ValidationError(f"Unsupported audio type '{file.content_type}'")

    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        raise ValidationError("Empty audio file")

    if len(audio_bytes) > max_bytes:
        raise ValidationError(f"Audio file exceeds maximum size of {settings.MAX_AUDIO_UPLOAD_MB} MB")

    stt = get_stt_provider()
    is_available = await stt.is_available()
    if not is_available:
        return TranscribeResponse(
            text=None,
            is_available=False,
            message="Speech-to-text is not configured on the backend. Please type your message.",
        )

    try:
        result = await stt.transcribe(audio_bytes=audio_bytes, filename=file.filename or "recording.m4a")
        return TranscribeResponse(
            text=result.text,
            is_available=True,
            message="Audio transcribed successfully",
        )
    except Exception as exc:
        return TranscribeResponse(
            text=None,
            is_available=False,
            message=f"Transcription failed: {str(exc)}",
        )


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_speech(
    req: SynthesizeRequest,
    membership: FamilyMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
):
    """Synthesize speech audio from text."""
    decision = await _engine.evaluate(
        db=db,
        principal_membership_id=membership.id,
        family_id=membership.family_id,
        resource=RA.VOICE_SPEECH_GENERATE[0],
        action=RA.VOICE_SPEECH_GENERATE[1],
        purpose="Generate speech audio",
    )
    if decision.effect == "DENY":
        raise PermissionDenied(decision.human_readable_reason)

    tts = get_tts_provider()
    is_available = await tts.is_available()
    if not is_available:
        return SynthesizeResponse(
            audio_url=None,
            is_available=False,
            message="Text-to-speech is not configured on the backend.",
        )

    try:
        result = await tts.synthesize(text=req.text)
        return SynthesizeResponse(
            audio_url="data:audio/mpeg;base64,...",
            is_available=True,
            message="Speech generated",
        )
    except Exception as exc:
        return SynthesizeResponse(
            audio_url=None,
            is_available=False,
            message=f"Synthesis failed: {str(exc)}",
        )
