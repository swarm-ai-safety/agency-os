"""OpenAI provider implementation using httpx."""

from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator

import httpx

from agency_os.gateway.providers.base import (
    CompletionChunk,
    CompletionResult,
    LLMProvider,
    TokenUsage,
)

logger = logging.getLogger(__name__)

OPENAI_API_BASE = "https://api.openai.com/v1"


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible chat completions via httpx.

    Works with OpenAI, Together, Fireworks, Groq, Ollama, and any
    endpoint that implements the OpenAI chat completions API.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        require_api_key: bool = True,
    ) -> None:
        self._api_key = api_key or os.environ.get(api_key_env, "")
        if require_api_key and not self._api_key:
            raise RuntimeError(f"{api_key_env} is not set")
        self._base_url = (base_url or OPENAI_API_BASE).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

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
        body: dict = {"model": model, "messages": messages, "stream": stream}
        if stream:
            body["stream_options"] = {"include_usage": True}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if top_p is not None:
            body["top_p"] = top_p
        if stop is not None:
            body["stop"] = stop
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
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return CompletionResult(
            content=choice["message"]["content"] or "",
            model=data["model"],
            finish_reason=choice.get("finish_reason", "stop"),
            usage=TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
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
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        return
                    data = json.loads(payload)
                    choice = data["choices"][0] if data.get("choices") else {}
                    delta = choice.get("delta", {})
                    usage_data = data.get("usage")
                    usage = None
                    if usage_data:
                        usage = TokenUsage(
                            prompt_tokens=usage_data.get("prompt_tokens", 0),
                            completion_tokens=usage_data.get("completion_tokens", 0),
                            total_tokens=usage_data.get("total_tokens", 0),
                        )
                    yield CompletionChunk(
                        delta_content=delta.get("content", "") or "",
                        model=data.get("model", model),
                        finish_reason=choice.get("finish_reason"),
                        usage=usage,
                    )
