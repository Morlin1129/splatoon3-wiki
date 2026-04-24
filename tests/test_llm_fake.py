from pipeline.llm.fake import FakeLLMProvider


def test_fake_returns_canned_responses_in_order() -> None:
    provider = FakeLLMProvider(responses=["first", "second"])
    assert provider.complete(system="s", user="u", model="m", max_tokens=10) == "first"
    assert provider.complete(system="s", user="u", model="m", max_tokens=10) == "second"


def test_fake_records_calls() -> None:
    provider = FakeLLMProvider(responses=["only"])
    provider.complete(system="sys", user="usr", model="mdl", max_tokens=7)

    assert provider.calls[0].system == "sys"
    assert provider.calls[0].user == "usr"
    assert provider.calls[0].model == "mdl"
    assert provider.calls[0].max_tokens == 7


def test_fake_raises_when_exhausted() -> None:
    import pytest

    provider = FakeLLMProvider(responses=[])
    with pytest.raises(AssertionError, match="exhausted"):
        provider.complete(system="s", user="u", model="m", max_tokens=1)
