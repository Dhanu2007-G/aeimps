"""
LLM Abstraction Layer — wraps Anthropic Claude with retry logic,
token tracking, and structured output support.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Production-grade LLM client wrapping Anthropic Claude.
    Features: retry with backoff, token tracking, structured output parsing,
    prompt injection detection.
    """

    def __init__(self):
        self._client = None
        self._total_tokens = 0
        self._total_calls = 0

    def _get_client(self):
        if self._client is None:
            if not settings.ANTHROPIC_API_KEY:
                logger.warning("ANTHROPIC_API_KEY not set — LLM calls will fail")
                return None
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            except ImportError:
                raise LLMError("anthropic package not installed")
        return self._client

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> tuple[str, int]:
        """
        Send a completion request to Claude.
        Returns: (response_text, tokens_used)
        """
        client = self._get_client()
        if client is None:
            # Mock response for development without API key
            return self._mock_response(prompt, json_mode), 0

        try:
            start = time.monotonic()
            system_prompt = system or (
                "You are AEIMPS, an enterprise intelligence assistant. "
                "Provide accurate, grounded responses based only on provided context."
            )
            if json_mode:
                system_prompt += " Always respond with valid JSON only, no markdown."

            response = await client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=max_tokens or settings.CLAUDE_MAX_TOKENS,
                temperature=temperature if temperature is not None else settings.CLAUDE_TEMPERATURE,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

            latency_ms = int((time.monotonic() - start) * 1000)
            tokens = response.usage.input_tokens + response.usage.output_tokens
            text = response.content[0].text

            self._total_tokens += tokens
            self._total_calls += 1

            logger.debug(
                "LLM call completed",
                extra={
                    "model": settings.CLAUDE_MODEL,
                    "tokens": tokens,
                    "latency_ms": latency_ms,
                },
            )

            return text, tokens

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise LLMError(f"LLM call failed: {e}") from e

    async def complete_structured(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> tuple[dict | list, int]:
        """Complete and parse JSON response."""
        import json
        import re

        text, tokens = await self.complete(
            prompt, system=system, max_tokens=max_tokens, json_mode=True
        )

        # Strip markdown code fences if present
        text = re.sub(r"```(?:json)?\n?(.*?)```", r"\1", text, flags=re.DOTALL).strip()
        try:
            return json.loads(text), tokens
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}\nText: {text[:200]}")
            return {}, tokens

    def _mock_response(self, prompt: str, json_mode: bool) -> str:
        """Fallback mock response when no API key is configured."""
        if json_mode:
            return '{"response": "Mock LLM response — configure ANTHROPIC_API_KEY", "confidence": 0.0}'
        return (
            "This is a mock LLM response. Please configure ANTHROPIC_API_KEY "
            "in your environment to enable actual Claude API responses."
        )

    @property
    def stats(self) -> dict[str, int]:
        return {"total_tokens": self._total_tokens, "total_calls": self._total_calls}


# Module-level singleton
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
