from types import SimpleNamespace

import pytest


def _make_mock_client(captured: dict) -> SimpleNamespace:
    class MockMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="mocked reply")])

    return SimpleNamespace(messages=MockMessages())


def test_anthropic_provider_passes_arguments_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    import pipeline.llm.anthropic_provider as mod

    monkeypatch.setattr(mod, "_build_client", lambda: _make_mock_client(captured))
    provider = mod.AnthropicProvider()

    out = provider.complete(
        system="sys prompt",
        user="user prompt",
        model="claude-sonnet-4-6",
        max_tokens=1024,
    )

    assert out == "mocked reply"
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["max_tokens"] == 1024
    assert captured["system"] == "sys prompt"
    assert captured["messages"] == [{"role": "user", "content": "user prompt"}]


def test_anthropic_provider_enforces_json_via_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    import pipeline.llm.anthropic_provider as mod

    monkeypatch.setattr(mod, "_build_client", lambda: _make_mock_client(captured))
    provider = mod.AnthropicProvider()

    provider.complete(
        system="sys prompt",
        user="u",
        model="claude-sonnet-4-6",
        max_tokens=100,
        response_format="json",
    )

    assert "sys prompt" in captured["system"]
    assert "JSON" in captured["system"]
