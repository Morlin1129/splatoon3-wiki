from types import SimpleNamespace

import pytest


def _make_mock_client(captured: dict) -> SimpleNamespace:
    class MockModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="gemini mock reply")

    return SimpleNamespace(models=MockModels())


def test_gemini_provider_passes_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    import pipeline.llm.gemini_provider as mod

    monkeypatch.setattr(mod, "_build_client", lambda: _make_mock_client(captured))
    provider = mod.GeminiProvider()

    out = provider.complete(
        system="sys prompt",
        user="user prompt",
        model="gemini-2.5-flash",
        max_tokens=512,
    )

    assert out == "gemini mock reply"
    assert captured["model"] == "gemini-2.5-flash"
    # google-genai passes system + user via config and contents respectively
    assert "user prompt" in str(captured["contents"])
