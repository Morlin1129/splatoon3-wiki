from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Protocol

from pipeline.config import StageConfig

ResponseFormat = Literal["text", "json"]


class LLMProvider(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: ResponseFormat = "text",
    ) -> str: ...


@dataclass
class CallRecord:
    system: str
    user: str
    model: str
    max_tokens: int
    response_format: ResponseFormat


def get_provider(cfg: StageConfig, *, fake_responses: list[str] | None = None) -> LLMProvider:
    if cfg.provider == "fake":
        from pipeline.llm.fake import FakeLLMProvider

        return FakeLLMProvider(responses=fake_responses or [])
    if cfg.provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from pipeline.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if cfg.provider == "gemini":
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY not set")
        from pipeline.llm.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise ValueError(f"unknown provider: {cfg.provider}")
