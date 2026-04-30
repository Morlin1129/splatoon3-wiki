from pathlib import Path

import pytest

from pipeline.config import (
    Category,
    PipelineConfig,
    StageConfig,
    load_categories,
    load_pipeline,
)


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


def test_category_with_no_fixed_levels(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: 01-principles
    label: 原理原則
    description: 普遍理論
    fixed_levels: []
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cats = load_categories(p)
    assert len(cats) == 1
    assert cats[0].fixed_levels == []


def test_category_with_enumerated_level(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: 02-rule-stage
    label: ルール×ステージ
    description: x
    fixed_levels:
      - name: ルール
        mode: enumerated
        values:
          - id: area
            label: ガチエリア
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cats = load_categories(p)
    assert len(cats[0].fixed_levels) == 1
    lvl = cats[0].fixed_levels[0]
    assert lvl.mode == "enumerated"
    assert lvl.name == "ルール"
    assert lvl.values is not None
    assert lvl.values[0].id == "area"
    assert lvl.values[0].label == "ガチエリア"


def test_category_with_open_level(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: 05-glossary
    label: 用語集
    description: x
    fixed_levels:
      - name: 用語カテゴリ
        mode: open
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cats = load_categories(p)
    lvl = cats[0].fixed_levels[0]
    assert lvl.mode == "open"
    assert lvl.values is None
    assert lvl.values_by_parent is None


def test_category_with_values_by_parent(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: 03-weapon-role
    label: ブキ・役割
    description: x
    fixed_levels:
      - name: ブキ種別
        mode: enumerated
        values:
          - id: shooter
            label: シューター
          - id: roller
            label: ローラー
      - name: 個別ブキ
        mode: enumerated
        values_by_parent:
          shooter:
            - id: splash-shooter
              label: スプラシューター
          roller:
            - id: splat-roller
              label: スプラローラー
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cats = load_categories(p)
    levels = cats[0].fixed_levels
    assert levels[1].values_by_parent is not None
    assert "shooter" in levels[1].values_by_parent
    assert levels[1].values_by_parent["shooter"][0].id == "splash-shooter"


def test_open_mode_with_values_is_invalid(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: x
    label: x
    description: x
    fixed_levels:
      - name: lv1
        mode: open
        values:
          - id: a
            label: a
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="open"):
        load_categories(p)


def test_enumerated_mode_without_values_is_invalid(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: x
    label: x
    description: x
    fixed_levels:
      - name: lv1
        mode: enumerated
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="enumerated"):
        load_categories(p)


def test_enumerated_mode_with_empty_values_is_invalid(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: x
    label: x
    description: x
    fixed_levels:
      - name: lv1
        mode: enumerated
        values: []
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="at least one value"):
        load_categories(p)


def test_values_by_parent_at_top_level_is_invalid(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: x
    label: x
    description: x
    fixed_levels:
      - name: lv0
        mode: enumerated
        values_by_parent:
          somekey:
            - id: a
              label: a
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="top level"):
        load_categories(p)


def test_values_by_parent_keys_must_match_parent_ids(tmp_path: Path) -> None:
    # parent (lv0) has [shooter, roller] but values_by_parent only has [shooter]
    yaml_text = """
categories:
  - id: x
    label: x
    description: x
    fixed_levels:
      - name: lv0
        mode: enumerated
        values:
          - id: shooter
            label: シューター
          - id: roller
            label: ローラー
      - name: lv1
        mode: enumerated
        values_by_parent:
          shooter:
            - id: a
              label: a
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="values_by_parent"):
        load_categories(p)
