"""Unit tests for voice transcription and synthesis endpoints."""
from __future__ import annotations

import io
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_transcribe_unauthorized(client: AsyncClient):
    """Calling voice transcription without auth token returns 401."""
    files = {"file": ("audio.wav", io.BytesIO(b"RIFFdummydata"), "audio/wav")}
    resp = await client.post("/api/v1/voice/transcribe", files=files)
    assert resp.status_code == 401


async def test_transcribe_disabled_provider_message(client: AsyncClient, admin_headers):
    """When STT is disabled, returns is_available=False with a clear message to type."""
    files = {"file": ("audio.wav", io.BytesIO(b"RIFF1234567890"), "audio/wav")}
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_available"] is False
    assert "not configured" in data["message"].lower() or "type your message" in data["message"].lower()


async def test_transcribe_empty_file_rejected(client: AsyncClient, admin_headers):
    """Empty audio payload returns 422 validation error."""
    files = {"file": ("empty.wav", io.BytesIO(b""), "audio/wav")}
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=admin_headers)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
