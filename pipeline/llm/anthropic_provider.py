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
        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text
