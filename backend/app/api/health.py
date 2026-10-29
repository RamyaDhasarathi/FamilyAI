"""Health and system status endpoints."""
from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.providers.llm.factory import get_llm_provider
from app.providers.products.factory import get_product_provider
from app.providers.speech_to_text.factory import get_stt_provider
from app.providers.text_to_speech.factory import get_tts_provider

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Basic liveness probe."""
    settings = get_settings()
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }


@router.get("/api/v1/system/status")
async def system_status(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Detailed runtime status of subsystems without leaking secrets."""
    settings = get_settings()

    # DB status
    db_status = "unavailable"
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "error"

    # LLM status
    llm = get_llm_provider()
    llm_available = False
    try:
        llm_available = await llm.is_available()
    except Exception:
        pass

    # STT & TTS status
    stt = get_stt_provider()
    stt_available = False
    try:
        stt_available = await stt.is_available()
    except Exception:
        pass

    tts = get_tts_provider()
    tts_available = False
    try:
        tts_available = await tts.is_available()
    except Exception:
        pass

    return {
        "backend": "online",
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "is_development": settings.is_development,
        "database": {
            "status": db_status,
            "engine": "sqlite" if "sqlite" in settings.DATABASE_URL else "postgresql",
        },
        "llm": {
            "provider": llm.provider_name,
            "model": settings.LLM_MODEL,
            "is_available": llm_available,
            "external_inference_enabled": settings.ENABLE_EXTERNAL_CLOUD_INFERENCE,
        },
        "products": {
            "provider": settings.PRODUCT_PROVIDER,
            "mode": "development_catalogue" if settings.PRODUCT_PROVIDER == "development_catalogue" else "real_provider",
        },
        "voice": {
            "stt_provider": stt.provider_name,
            "stt_available": stt_available,
            "tts_provider": tts.provider_name,
            "tts_available": tts_available,
        },
        "features": {
            "simulation_allowed": settings.ALLOW_DEVELOPMENT_SIMULATION,
        },
    }
