"""OpenAI-compatible LLM provider (works with Ollama, vLLM, OpenAI API, etc.)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.exceptions import ProviderUnavailable
from app.providers.llm.base import BaseLLMProvider, ChatMessage, LLMResponse

logger = logging.getLogger(__name__)

_OPENAI_BASE = "https://api.openai.com"


class OpenAICompatibleProvider(BaseLLMProvider):
    """Provider that speaks the OpenAI Chat Completions API.

    Compatible with:
    - OpenAI (api.openai.com)
    - Ollama (http://localhost:11434/v1)
    - vLLM (http://localhost:8000/v1)
    - Any server that implements ``POST /v1/chat/completions``.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        timeout_seconds: int = 60,
        enable_external_cloud_inference: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key or ""
        self._timeout = timeout_seconds
        self._enable_external_cloud = enable_external_cloud_inference

    # ------------------------------------------------------------------
    # BaseLLMProvider implementation
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:  # noqa: D102
        return "openai_compatible"

    async def is_available(self) -> bool:
        """Probe the /models endpoint to see if the server is reachable."""
        if self._is_cloud_blocked():
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers=self._auth_headers(),
                )
                return resp.status_code < 500
        except Exception:  # noqa: BLE001
            return False

    async def chat(self, messages: List[ChatMessage], **kwargs: Any) -> LLMResponse:
        """Call the Chat Completions endpoint and return a normalised response.

        Args:
            messages: Conversation history.
            **kwargs: Optional overrides such as ``temperature``, ``max_tokens``.

        Returns:
            :class:`LLMResponse` with the model reply.

        Raises:
            :class:`ProviderUnavailable`: If external cloud inference is
                blocked by configuration, or on unrecoverable network errors.
        """
        if self._is_cloud_blocked():
            raise ProviderUnavailable("openai_compatible")

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": [m.model_dump() for m in messages],
        }
        # Allow caller to override temperature / max_tokens etc.
        payload.update(
            {
                k: v
                for k, v in kwargs.items()
                if k in {"temperature", "max_tokens", "top_p", "stream"}
            }
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        **self._auth_headers(),
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            logger.error("LLM request timed out after %ss: %s", self._timeout, exc)
            return LLMResponse(
                content=(
                    "I'm sorry, the AI service took too long to respond. "
                    "Please try again in a moment."
                ),
                provider=self.provider_name,
                model=self._model,
            )
        except httpx.ConnectError as exc:
            logger.error("LLM connection error: %s", exc)
            return LLMResponse(
                content=(
                    "I'm unable to reach the AI service right now. "
                    "Please check that the service is running and try again."
                ),
                provider=self.provider_name,
                model=self._model,
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "LLM HTTP error %s: %s", exc.response.status_code, exc.response.text
            )
            return LLMResponse(
                content=(
                    f"The AI service returned an error (HTTP {exc.response.status_code}). "
                    "Please try again later."
                ),
                provider=self.provider_name,
                model=self._model,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected LLM error: %s", exc)
            return LLMResponse(
                content="An unexpected error occurred while contacting the AI service.",
                provider=self.provider_name,
                model=self._model,
            )

        # Parse the OpenAI-format response envelope.
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = data.get("usage", {})
            model_used = data.get("model", self._model)
        except (KeyError, IndexError, TypeError) as exc:
            logger.error("Malformed LLM response: %s — raw: %s", exc, data)
            return LLMResponse(
                content="The AI service returned an unexpected response format.",
                provider=self.provider_name,
                model=self._model,
            )

        return LLMResponse(
            content=content,
            is_mock=False,
            provider=self.provider_name,
            model=model_used,
            usage=usage,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_cloud_blocked(self) -> bool:
        """Return True if calling OpenAI directly is forbidden by config."""
        return (
            not self._enable_external_cloud
            and self._base_url.startswith(_OPENAI_BASE)
        )

    def _auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
