from pathlib import Path

import pytest

from pipeline.llm.parsing import parse_json_response, strip_markdown_fence


def test_strip_fence_with_json_label() -> None:
    text = '```json\n{"a": 1}\n```'
    assert strip_markdown_fence(text) == '{"a": 1}'


def test_strip_fence_without_label() -> None:
    text = "```\n[1, 2, 3]\n```"
    assert strip_markdown_fence(text) == "[1, 2, 3]"


def test_strip_fence_passthrough_when_no_fence() -> None:
    text = '{"already": "clean"}'
    assert strip_markdown_fence(text) == text


def test_parse_json_response_handles_fenced_response(tmp_path: Path) -> None:
    raw = '```json\n{"category": "01-principles", "subtopic": "x"}\n```'
    result = parse_json_response(raw, stage="classify", debug_dir=tmp_path / "debug")
    assert result == {"category": "01-principles", "subtopic": "x"}
    saved = (tmp_path / "debug" / "classify.txt").read_text(encoding="utf-8")
    assert saved == raw


def test_parse_json_response_raises_with_snippet_on_failure(tmp_path: Path) -> None:
    raw = '{"category": "missing-quote'
    with pytest.raises(ValueError, match="non-JSON response"):
        parse_json_response(raw, stage="classify", debug_dir=tmp_path / "debug")
    saved = (tmp_path / "debug" / "classify.txt").read_text(encoding="utf-8")
    assert saved == raw


def test_parse_json_response_no_debug_dir_works(tmp_path: Path) -> None:
    result = parse_json_response("[1, 2]", stage="ingest", debug_dir=None)
    assert result == [1, 2]
