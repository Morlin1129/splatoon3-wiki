from __future__ import annotations

import os

from google import genai
from google.genai import types as genai_types

from pipeline.llm.base import ResponseFormat


def _build_client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


class GeminiProvider:
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
        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if response_format == "json" else "text/plain",
        )
        response = self._client.models.generate_content(
            model=model,
            contents=user,
            config=config,
        )
        return response.text
