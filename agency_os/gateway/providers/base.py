"""Abstract LLM provider interface and shared data types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class TokenUsage:
    """Token counts from a completion."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class CompletionResult:
    """Non-streaming completion response."""

    content: str
    model: str
    usage: TokenUsage
    finish_reason: str = "stop"


@dataclass
class CompletionChunk:
    """A single chunk in a streaming completion."""

    delta_content: str = ""
    model: str = ""
    finish_reason: str | None = None
    usage: TokenUsage | None = None


class LLMProvider(ABC):
    """Abstract base for LLM API providers."""

    @abstractmethod
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
        """Send a non-streaming chat completion request."""
        ...

    @abstractmethod
    def chat_completion_stream(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
    ) -> AsyncIterator[CompletionChunk]:
        """Send a streaming chat completion request."""
        ...
