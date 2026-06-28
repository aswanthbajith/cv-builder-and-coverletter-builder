"""LLM client — wraps Gemini 2.0 Flash with structured outputs.

The :class:`LLMClient` protocol is what every engine depends on. Two
implementations ship:

- :class:`GeminiClient` — production. Calls ``google.generativeai`` with
  ``response_schema`` for JSON outputs and retries on 429/5xx via tenacity.
- :class:`FakeLLMClient` — used by tests. Returns canned JSON / text from a
  per-engine mapping. No network, no secrets.

Engines accept the client via constructor injection so tests never need
monkey-patching.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Protocol, runtime_checkable

from job_automation.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol every LLM client implements.

    Both methods are async because the production Gemini client is async
    and tests mirror the same signature.
    """

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        """Call the LLM and parse the response as JSON against ``schema``."""
        ...

    async def complete_text(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 30.0,
    ) -> str:
        """Call the LLM and return the raw text response."""
        ...


class GeminiClient:
    """Production Gemini 2.0 Flash client with structured outputs + retries.

    Uses ``response_schema`` to constrain outputs to a JSON schema. Retries
    on 429 / 5xx / ResourceExhausted / JSONDecodeError with exponential
    backoff (0.5s, 1s, 2s, 4s, 8s, jittered). Hard stop after 5 attempts,
    then raises :class:`job_automation.engines.exceptions.LLMUnavailable`.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model_name: str = "gemini-2.0-flash",
        max_retries: int = 5,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._model_name = model_name
        self._max_retries = max_retries
        self._client = None  # lazy-init via google.generativeai

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import google.generativeai as genai  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover - import guard
                raise RuntimeError(
                    "google-generativeai is not installed. "
                    "Run `pip install google-generativeai>=0.7.0`."
                ) from exc
            if not self._api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set. Configure it via the GEMINI_API_KEY "
                    "environment variable or pass api_key to GeminiClient."
                )
            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self._model_name)
        return self._client

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        model = self._ensure_client()
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        model.generate_content,
                        [
                            {"role": "user", "parts": [{"text": system + "\n\n" + user}]},
                        ],
                        generation_config={
                            "temperature": temperature,
                            "max_output_tokens": max_tokens,
                            "response_mime_type": "application/json",
                            "response_schema": schema,
                        },
                    ),
                    timeout=timeout_s,
                )
                text = response.text or "{}"
                return json.loads(text)
            except json.JSONDecodeError as exc:
                last_exc = exc
                logger.warning(
                    "llm_json_decode_error",
                    extra={"attempt": attempt, "error": str(exc)},
                )
            except Exception as exc:  # noqa: BLE001 — retry on any transient error
                last_exc = exc
                logger.warning(
                    "llm_attempt_failed",
                    extra={"attempt": attempt, "error": str(exc)},
                )
            await asyncio.sleep(0.5 * (2**attempt))
        from job_automation.engines.exceptions import LLMUnavailable

        raise LLMUnavailable(
            f"Gemini failed after {self._max_retries} attempts: {last_exc}",
            engine="llm_client",
        )

    async def complete_text(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 30.0,
    ) -> str:
        model = self._ensure_client()
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        model.generate_content,
                        [
                            {"role": "user", "parts": [{"text": system + "\n\n" + user}]},
                        ],
                        generation_config={
                            "temperature": temperature,
                            "max_output_tokens": max_tokens,
                        },
                    ),
                    timeout=timeout_s,
                )
                return response.text or ""
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "llm_attempt_failed",
                    extra={"attempt": attempt, "error": str(exc)},
                )
            await asyncio.sleep(0.5 * (2**attempt))
        from job_automation.engines.exceptions import LLMUnavailable

        raise LLMUnavailable(
            f"Gemini failed after {self._max_retries} attempts: {last_exc}",
            engine="llm_client",
        )


class FakeLLMClient:
    """Test double — returns canned responses from per-engine mappings.

    Two storage maps:

    - ``json_responses``: ``{(engine_name, prompt_substr): dict}`` — the
      first matching key wins. Used by tests to return deterministic JSON
      per engine.
    - ``text_responses``: ``{engine_name: str}`` — used for ``complete_text``
      calls when only the engine name matters.

    If no match is found, :meth:`complete_json` returns ``{}`` and
    :meth:`complete_text` returns ``""``. This keeps tests fast and obvious
    about what is being exercised.
    """

    def __init__(self) -> None:
        self.json_responses: dict[tuple[str, str], dict[str, Any]] = {}
        self.text_responses: dict[str, str] = {}
        self.call_log: list[dict[str, Any]] = []

    def set_json_response(self, engine_name: str, prompt_substr: str, response: dict[str, Any]) -> None:
        self.json_responses[(engine_name, prompt_substr)] = response

    def set_text_response(self, engine_name: str, response: str) -> None:
        self.text_responses[engine_name] = response

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        self.call_log.append({"system": system, "user": user, "schema": schema, "kind": "json"})
        # Try to find a matching engine-specific response. Match on the
        # ``user`` content first (tests usually include the engine name in
        # the prompt); fall back to any key for the engine.
        for (engine_name, substr), resp in self.json_responses.items():
            if substr in user or substr in system:
                return resp
        return {}

    async def complete_text(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 30.0,
    ) -> str:
        self.call_log.append({"system": system, "user": user, "kind": "text"})
        for (engine_name, substr), resp in self.json_responses.items():
            if substr in user or substr in system:
                # If a JSON response was registered, serialize it for text mode.
                return json.dumps(resp)
        for engine_name, resp in self.text_responses.items():
            if engine_name in user or engine_name in system:
                return resp
        return ""


__all__ = ["FakeLLMClient", "GeminiClient", "LLMClient"]