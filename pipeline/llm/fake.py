from __future__ import annotations

from pipeline.llm.base import CallRecord, ResponseFormat


class FakeLLMProvider:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[CallRecord] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: ResponseFormat = "text",
    ) -> str:
        self.calls.append(
            CallRecord(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        )
        assert self._responses, "FakeLLMProvider response queue exhausted"
        return self._responses.pop(0)
