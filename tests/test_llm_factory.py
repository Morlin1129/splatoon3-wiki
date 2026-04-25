import pytest

from pipeline.config import StageConfig
from pipeline.llm.base import get_provider
from pipeline.llm.fake import FakeLLMProvider


def test_get_provider_returns_fake_instance() -> None:
    cfg = StageConfig(provider="fake", model="irrelevant", max_tokens=1)
    provider = get_provider(cfg, fake_responses=["ok"])

    assert isinstance(provider, FakeLLMProvider)


def test_get_provider_raises_for_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = StageConfig(provider="anthropic", model="claude-sonnet-4-6", max_tokens=100)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_provider(cfg)
