from __future__ import annotations

import os

import anthropic

from pipeline.llm.base import ResponseFormat


def _build_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


class AnthropicProvider:
    def __init__(self) -> None:
        self._client = _build_client()

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: ResponseFormat = "text",
    ) -> str:
        # Anthropic has no native `response_mime_type` like Gemini. When JSON is
        # requested, fall back to a prompt-level enforcement so callers relying
        # on `response_format="json"` still get valid JSON.
        effective_system = (
            f"{system}\n\nIMPORTANT: respond with valid JSON only. "
            "No markdown code fences, no prose outside the JSON."
            if response_format == "json"
            else system
        )
        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=effective_system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text
