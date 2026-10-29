"""Voice: a spoken question or a voice note, turned into words.

Two engines behind one call. The default is **local**: faster-whisper on this
machine, so a family's voice (a parent describing a symptom, a grandparent
saying an amount) never leaves the deployment. **Cloud** is an opt-in for a
deployment that wants the accuracy of a hosted Indic-language model: the audio
goes to one OpenAI-compatible transcription endpoint named in settings, and
nowhere else. **Off** refuses.

What is never done: the audio is not stored, anywhere, by either engine; the
audit records that a transcription happened (engine, seconds, language), never
the words; and nothing is acted on from a transcript on its own: a spoken
question is answered as a typed one is, a spoken note is filed as the member's
own private note, and nothing is paid, booked or sent.

Honest limits: the small local model is good at English and workable in Hindi;
Tamil, Telugu and code-switched speech are better with `voice_model=large-v3`
(slower, 3 GB) or the cloud engine. A transcript can be wrong, so what was
heard is always said back before it is filed.
"""
from __future__ import annotations

import asyncio
import io
import logging
import tempfile
from dataclasses import dataclass

from familyos import audit
from familyos.identity import Invalid, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

MAX_BYTES = 12 * 1024 * 1024
_model = None
_lock = asyncio.Lock()


class VoiceUnavailable(Invalid):
    """Voice is off, or its engine could not be reached."""


@dataclass
class Transcript:
    text: str
    language: str | None
    seconds: float | None
    engine: str


def _local_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(settings.voice_model, device=settings.voice_device, compute_type=settings.voice_compute)
    return _model


def _run_local(data: bytes) -> Transcript:
    with tempfile.NamedTemporaryFile(suffix=".audio") as f:
        f.write(data)
        f.flush()
        segments, info = _local_model().transcribe(f.name, beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
    return Transcript(text, getattr(info, "language", None), getattr(info, "duration", None), "local")


async def _run_cloud(data: bytes, content_type: str) -> Transcript:
    import httpx
    if not settings.voice_cloud_url:
        raise VoiceUnavailable("the cloud voice engine has no address set")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(settings.voice_cloud_url.rstrip("/") + "/audio/transcriptions",
                              headers={"Authorization": f"Bearer {settings.voice_cloud_key}"} if settings.voice_cloud_key else {},
                              data={"model": settings.voice_cloud_model, "response_format": "verbose_json"},
                              files={"file": ("voice", io.BytesIO(data), content_type or "audio/ogg")})
    if r.status_code >= 400:
        raise VoiceUnavailable(f"the cloud voice engine answered {r.status_code}")
    body = r.json()
    return Transcript((body.get("text") or "").strip(), body.get("language"), body.get("duration"), "cloud")


async def transcribe(p: Principal, data: bytes, content_type: str | None = None, *, via: str = "api") -> Transcript:
    """Words from audio, for a member. Raises VoiceUnavailable when voice is off
    or its engine fails, Invalid for audio that is too big or too long."""
    engine = (settings.voice_engine or "off").lower()
    if engine == "off":
        raise VoiceUnavailable("voice is switched off on this deployment")
    if not data:
        raise Invalid("no audio was sent")
    if len(data) > MAX_BYTES:
        raise Invalid("that recording is too large; keep it under a few minutes")
    try:
        if engine == "cloud":
            out = await _run_cloud(data, content_type or "")
        else:
            async with _lock:     # one model, one transcription at a time
                out = await asyncio.to_thread(_run_local, data)
    except VoiceUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - the engine's own failure, said plainly
        logger.warning("voice transcription failed", exc_info=True)
        raise VoiceUnavailable(f"the {engine} voice engine could not read that ({type(exc).__name__})") from exc
    if out.seconds and out.seconds > settings.voice_max_seconds:
        raise Invalid(f"that recording is {int(out.seconds)} seconds; voice notes are read up to {settings.voice_max_seconds}")
    await audit.record(p.household_id, "voice.transcribed", actor_member_id=p.member_id,
                       detail={"engine": out.engine, "seconds": round(out.seconds or 0), "language": out.language, "via": via, "words": len(out.text.split())})
    return out
