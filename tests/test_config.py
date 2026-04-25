from pathlib import Path

import pytest

from pipeline.config import Category, PipelineConfig, StageConfig, load_categories, load_pipeline


def test_load_categories(tmp_path: Path) -> None:
    yaml_path = tmp_path / "categories.yaml"
    yaml_path.write_text(
        "categories:\n"
        "  - id: 01-principles\n"
        "    label: 原理原則\n"
        "    description: 普遍理論\n"
        "  - id: 02-rule-stage\n"
        "    label: ルール×ステージ\n"
        "    description: 定石\n",
        encoding="utf-8",
    )

    result = load_categories(yaml_path)

    assert result == [
        Category(id="01-principles", label="原理原則", description="普遍理論"),
        Category(id="02-rule-stage", label="ルール×ステージ", description="定石"),
    ]


def test_load_pipeline(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(
        "stages:\n"
        "  ingest:\n"
        "    provider: gemini\n"
        "    model: gemini-2.5-flash\n"
        "    max_tokens: 4096\n"
        "  classify:\n"
        "    provider: gemini\n"
        "    model: gemini-2.5-flash\n"
        "    max_tokens: 512\n"
        "  compile:\n"
        "    provider: anthropic\n"
        "    model: claude-sonnet-4-6\n"
        "    max_tokens: 8192\n",
        encoding="utf-8",
    )

    result = load_pipeline(yaml_path)

    assert isinstance(result, PipelineConfig)
    assert result.stages["ingest"] == StageConfig(
        provider="gemini", model="gemini-2.5-flash", max_tokens=4096
    )
    assert result.stages["compile"].provider == "anthropic"


def test_load_pipeline_rejects_unknown_provider(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(
        "stages:\n  ingest:\n    provider: bogus\n    model: x\n    max_tokens: 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="provider"):
        load_pipeline(yaml_path)
