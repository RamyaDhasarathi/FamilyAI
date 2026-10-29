"""LLM provider factory — selects the correct implementation from config."""
from __future__ import annotations

import logging

from app.core.config import get_settings
from app.providers.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_provider_instance: BaseLLMProvider | None = None


def get_llm_provider() -> BaseLLMProvider:
    """Return the singleton LLM provider as configured in settings.

    Supported values for ``LLM_PROVIDER``:
    - ``mock``  – deterministic mock (default for development)
    - ``ollama`` / ``openai_compatible`` – any OpenAI-compatible endpoint

    Returns:
        A concrete :class:`BaseLLMProvider` instance.
    """
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    settings = get_settings()
    provider_name = settings.LLM_PROVIDER.lower().strip()

    if provider_name == "mock":
        from app.providers.llm.mock_provider import MockLLMProvider

        _provider_instance = MockLLMProvider()
        logger.info("LLM provider: mock (deterministic)")

    elif provider_name in {"openai_compatible", "ollama", "vllm", "openai"}:
        from app.providers.llm.openai_compatible import OpenAICompatibleProvider

        _provider_instance = OpenAICompatibleProvider(
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY or None,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            enable_external_cloud_inference=settings.ENABLE_EXTERNAL_CLOUD_INFERENCE,
        )
        logger.info(
            "LLM provider: openai_compatible (base_url=%s model=%s)",
            settings.LLM_BASE_URL,
            settings.LLM_MODEL,
        )

    else:
        logger.warning(
            "Unknown LLM_PROVIDER=%r — falling back to mock", provider_name
        )
        from app.providers.llm.mock_provider import MockLLMProvider

        _provider_instance = MockLLMProvider()

    return _provider_instance


def reset_llm_provider() -> None:
    """Clear the cached provider singleton (useful in tests)."""
    global _provider_instance
    _provider_instance = None
