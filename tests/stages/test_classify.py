import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category, FixedLevel, LevelValue, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import ClassifiedFrontmatter, SnippetFrontmatter
from pipeline.stages import classify
from pipeline.state import Manifest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "snippets").mkdir()
    (tmp_path / "classified").mkdir()
    (tmp_path / "state").mkdir()
    return tmp_path


def _seed_snippet(workspace: Path, name: str, body: str) -> Path:
    path = workspace / "snippets" / name
    fm = SnippetFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
    )
    write_frontmatter(path, fm, body)
    return path


def test_classify_writes_path_to_classified(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "2026-04-01-abc.md", "右高台の制圧…")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        }
    ).save(manifest_path)

    categories = [
        Category(id="01-principles", label="原理原則", description="..."),
    ]
    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "01-principles", "path": ["dakai-fundamentals"]})]
    )

    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=categories,
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    out = workspace / "classified" / "01-principles" / "2026-04-01-abc.md"
    fm, _ = read_frontmatter(out, ClassifiedFrontmatter)
    assert fm.path == ["dakai-fundamentals"]


def test_classify_validates_enumerated_layer_id(workspace: Path) -> None:
    """When category has enumerated fixed level, the path[0] must be a known id."""
    snippet_path = _seed_snippet(workspace, "x.md", "本文")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        }
    ).save(manifest_path)

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
                )
            ],
        )
    ]
    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "03-weapon-role", "path": ["unknown-type"]})]
    )

    with pytest.raises(ValueError, match="enumerated"):
        classify.run(
            provider=provider,
            stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
            categories=categories,
            snippets_dir=workspace / "snippets",
            classified_dir=workspace / "classified",
            manifest_path=manifest_path,
            system_prompt="CLASSIFY PROMPT",
            root=workspace,
        )


def test_classify_uses_known_paths_cache_from_manifest(workspace: Path) -> None:
    """Existing classified paths are loaded from manifest cache, not by walking
    the classified dir."""
    snippet_path = _seed_snippet(workspace, "new.md", "新スニペット")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        },
        known_paths_cache={
            "01-principles": [["dakai-fundamentals"], ["frontline-fundamentals"]],
        },
    ).save(manifest_path)

    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "01-principles", "path": ["dakai-fundamentals"]})]
    )
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="原理原則", description="x")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    user_prompt = provider.calls[0].user
    assert "dakai-fundamentals" in user_prompt
    assert "frontline-fundamentals" in user_prompt


def test_classify_appends_new_path_to_cache(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "new.md", "本文")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        }
    ).save(manifest_path)

    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "01-principles", "path": ["new-topic"]})]
    )
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="x", description="x")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    reloaded = Manifest.load(manifest_path)
    assert reloaded.known_paths_cache.get("01-principles") == [["new-topic"]]
    assert reloaded.snippets[str(snippet_path.relative_to(workspace))]["classified_path"] == [
        "new-topic"
    ]


def test_classify_skips_already_classified(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "x.md", "...")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": True,
            }
        }
    ).save(manifest_path)

    provider = FakeLLMProvider(responses=[])
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="x", description="x")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )
    assert provider.calls == []
