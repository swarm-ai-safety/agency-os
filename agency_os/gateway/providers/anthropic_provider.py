"""Anthropic provider implementation using httpx.

Translates OpenAI-format messages to/from the Anthropic Messages API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator

import httpx

from agency_os.gateway.providers.base import (
    CompletionChunk,
    CompletionResult,
    LLMProvider,
    TokenUsage,
)

logger = logging.getLogger(__name__)

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API via httpx."""

    def __init__(self, api_key: str | None = None) -> None:
        api_key_value = api_key or os.environ.get("ANTHROPIC_API_KEY", "") or ""
        if not api_key_value:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._api_key: str = api_key_value

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _translate_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Extract system message and convert to Anthropic format.

        Returns (system_prompt, anthropic_messages).
        """
        system_prompt = None
        converted = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                converted.append({"role": msg["role"], "content": msg["content"]})
        return system_prompt, converted

    def _build_body(
        self,
        model: str,
        messages: list[dict],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
    ) -> dict:
        system_prompt, converted = self._translate_messages(messages)
        body: dict = {
            "model": model,
            "messages": converted,
            "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
            "stream": stream,
        }
        if system_prompt:
            body["system"] = system_prompt
        if temperature is not None:
            body["temperature"] = temperature
        if top_p is not None:
            body["top_p"] = top_p
        if stop is not None:
            body["stop_sequences"] = [stop] if isinstance(stop, str) else stop
        return body

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
    ) -> CompletionResult:
        body = self._build_body(
            model,
            messages,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{ANTHROPIC_API_BASE}/messages",
                headers=self._headers(),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract text from content blocks
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        return CompletionResult(
            content=content,
            model=data.get("model", model),
            finish_reason=_map_stop_reason(data.get("stop_reason", "end_turn")),
            usage=TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    async def chat_completion_stream(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
    ) -> AsyncIterator[CompletionChunk]:
        body = self._build_body(
            model,
            messages,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
        )
        input_tokens = 0
        output_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{ANTHROPIC_API_BASE}/messages",
                headers=self._headers(),
                json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    event_type = data.get("type", "")

                    if event_type == "message_start":
                        usage = data.get("message", {}).get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)

                    elif event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield CompletionChunk(
                                delta_content=delta.get("text", ""),
                                model=model,
                            )

                    elif event_type == "message_delta":
                        delta = data.get("delta", {})
                        usage = data.get("usage", {})
                        output_tokens = usage.get("output_tokens", 0)
                        yield CompletionChunk(
                            delta_content="",
                            model=model,
                            finish_reason=_map_stop_reason(
                                delta.get("stop_reason", "end_turn")
                            ),
                            usage=TokenUsage(
                                prompt_tokens=input_tokens,
                                completion_tokens=output_tokens,
                                total_tokens=input_tokens + output_tokens,
                            ),
                        )


def _map_stop_reason(reason: str) -> str:
    """Map Anthropic stop reasons to OpenAI finish_reason values."""
    return {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "max_tokens": "length",
    }.get(reason, reason)
