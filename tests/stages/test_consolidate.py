import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category, FixedLevel, LevelValue, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import ClassifiedFrontmatter
from pipeline.stages import consolidate


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "classified").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "state").mkdir()
    return tmp_path


def _seed_classified(
    workspace: Path, category: str, name: str, path: list[str], body: str = "本文"
) -> Path:
    file_path = workspace / "classified" / category / name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
        category=category,
        path=path,
    )
    write_frontmatter(file_path, fm, body)
    return file_path


def _categories_principles_only() -> list[Category]:
    return [Category(id="01-principles", label="原理原則", description="x")]


def test_consolidate_skips_when_path_frequency_unchanged(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "x.md", ["dakai-fundamentals"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    provider = FakeLLMProvider(responses=[json.dumps({"renames": []})])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )
    assert len(provider.calls) == 1

    provider = FakeLLMProvider(responses=[])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )
    assert provider.calls == []


def test_consolidate_calls_llm_when_path_frequency_changes(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "x.md", ["dakai-fundamentals"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    consolidate.run(
        provider=FakeLLMProvider(responses=[json.dumps({"renames": []})]),
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )

    _seed_classified(workspace, "01-principles", "y.md", ["new-topic"])

    provider = FakeLLMProvider(responses=[json.dumps({"renames": []})])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )
    assert len(provider.calls) == 1


def test_consolidate_applies_path_rename(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "x.md", ["old-name"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "renames": [
                        {
                            "category": "01-principles",
                            "from_path": ["old-name"],
                            "to_path": ["new-name"],
                            "reason": "テスト",
                        }
                    ]
                }
            )
        ]
    )
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )

    out = workspace / "classified" / "01-principles" / "x.md"
    fm, _ = read_frontmatter(out, ClassifiedFrontmatter)
    assert fm.path == ["new-name"]


def test_consolidate_rejects_rename_changing_enumerated_layer(workspace: Path) -> None:
    _seed_classified(workspace, "03-weapon-role", "x.md", ["shooter", "splash-shooter"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    categories = [
        Category(
            id="03-weapon-role",
            label="ブキ",
            description="x",
            fixed_levels=[
                FixedLevel(
                    name="ブキ種別",
                    mode="enumerated",
                    values=[
                        LevelValue(id="shooter", label="シューター"),
                        LevelValue(id="roller", label="ローラー"),
                    ],
                ),
                FixedLevel(
                    name="個別ブキ",
                    mode="enumerated",
                    values_by_parent={
                        "shooter": [LevelValue(id="splash-shooter", label="スプラ")],
                        "roller": [LevelValue(id="splat-roller", label="スプラローラー")],
                    },
                ),
            ],
        )
    ]
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "renames": [
                        {
                            "category": "03-weapon-role",
                            "from_path": ["shooter", "splash-shooter"],
                            "to_path": ["roller", "splat-roller"],
                            "reason": "x",
                        }
                    ]
                }
            )
        ]
    )
    with pytest.raises(ValueError, match="enumerated"):
        consolidate.run(
            provider=provider,
            stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
            categories=categories,
            classified_dir=workspace / "classified",
            wiki_dir=workspace / "wiki",
            log_path=workspace / "state" / "consolidate_log.md",
            manifest_path=manifest_path,
            system_prompt="x",
            now=lambda: datetime(2026, 4, 30),
            root=workspace,
        )


def test_consolidate_skips_enumerated_only_categories(workspace: Path) -> None:
    """If a category's fixed_levels are all enumerated AND no free tail exists,
    consolidate skips it entirely (no LLM call)."""
    _seed_classified(workspace, "03-weapon-role", "x.md", ["shooter", "splash-shooter"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    categories = [
        Category(
            id="03-weapon-role",
            label="ブキ",
            description="x",
            fixed_levels=[
                FixedLevel(
                    name="ブキ種別",
                    mode="enumerated",
                    values=[LevelValue(id="shooter", label="シューター")],
                ),
                FixedLevel(
                    name="個別ブキ",
                    mode="enumerated",
                    values_by_parent={"shooter": [LevelValue(id="splash-shooter", label="スプラ")]},
                ),
            ],
        )
    ]
    provider = FakeLLMProvider(responses=[])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=categories,
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )
    assert provider.calls == []
