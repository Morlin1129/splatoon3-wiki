import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category, StageConfig
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


def test_classify_moves_snippet_to_classified_dir(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "2026-04-01-abc.md", "右高台の制圧はリスク…")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    manifest = Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        },
    )
    manifest.save(manifest_path)

    categories = [
        Category(id="01-principles", label="原理原則", description="..."),
        Category(id="02-rule-stage", label="ルール×ステージ", description="..."),
    ]

    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "02-rule-stage", "subtopic": "海女美術-ガチエリア"})]
    )
    stage_cfg = StageConfig(provider="fake", model="x", max_tokens=512)

    classify.run(
        provider=provider,
        stage_cfg=stage_cfg,
        categories=categories,
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    out = workspace / "classified" / "02-rule-stage" / "2026-04-01-abc.md"
    assert out.exists()
    fm, body = read_frontmatter(out, ClassifiedFrontmatter)
    assert fm.category == "02-rule-stage"
    assert fm.subtopic == "海女美術-ガチエリア"
    assert "右高台" in body

    reloaded = Manifest.load(manifest_path)
    assert reloaded.snippets[str(snippet_path.relative_to(workspace))]["classified"] is True


def test_classify_skips_already_classified(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "2026-04-01-abc.md", "…")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    manifest = Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": True,
            }
        },
    )
    manifest.save(manifest_path)

    provider = FakeLLMProvider(responses=[])
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="x", description="y")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    assert provider.calls == []


def test_classify_passes_existing_frontmatter_subtopics_to_prompt(workspace: Path) -> None:
    # Pre-existing classified file with a clean (non-dated) subtopic in frontmatter
    classified_dir = workspace / "classified" / "01-principles"
    classified_dir.mkdir(parents=True)
    existing_fm = ClassifiedFrontmatter(
        source_file="sample_raw/old.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="hold",
        category="01-principles",
        subtopic="dakai-fundamentals",
    )
    write_frontmatter(
        classified_dir / "2026-04-01-old-snippet.md",
        existing_fm,
        "古いスニペット本文",
    )

    snippet_path = _seed_snippet(workspace, "2026-04-26-new.md", "新しいスニペット本文")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        },
    ).save(manifest_path)

    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "01-principles", "subtopic": "dakai-fundamentals"})]
    )
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="原理原則", description="...")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    assert len(provider.calls) == 1
    user_prompt = provider.calls[0].user
    # The clean frontmatter subtopic must be visible to the LLM
    assert "dakai-fundamentals" in user_prompt
    # The dated file stem must NOT appear (that was the bug)
    assert "2026-04-01-old-snippet" not in user_prompt
