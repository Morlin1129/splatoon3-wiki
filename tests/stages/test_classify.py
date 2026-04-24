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
    (tmp_path / "pipeline" / "prompts").mkdir(parents=True)
    (tmp_path / "pipeline" / "prompts" / "classify.md").write_text(
        "CLASSIFY PROMPT", encoding="utf-8"
    )
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
        prompt_path=workspace / "pipeline" / "prompts" / "classify.md",
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
        prompt_path=workspace / "pipeline" / "prompts" / "classify.md",
        root=workspace,
    )

    assert provider.calls == []
