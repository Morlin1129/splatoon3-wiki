import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.stages import compile as compile_stage
from pipeline.state import Manifest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "classified" / "02-rule-stage").mkdir(parents=True)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "pipeline" / "prompts").mkdir(parents=True)
    (tmp_path / "pipeline" / "prompts" / "compile.md").write_text(
        "COMPILE PROMPT", encoding="utf-8"
    )
    return tmp_path


def _seed_classified(path: Path, subtopic: str, body: str) -> None:
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/a.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
        category="02-rule-stage",
        subtopic=subtopic,
    )
    write_frontmatter(path, fm, body)


def test_compile_writes_wiki_page_with_frontmatter_and_sources(workspace: Path) -> None:
    _seed_classified(
        workspace / "classified" / "02-rule-stage" / "a.md",
        "海女美術-ガチエリア",
        "右高台の制圧はリスクあり。",
    )

    clusters_path = workspace / "state" / "clusters.json"
    clusters_path.write_text(
        json.dumps(
            {"02-rule-stage/海女美術-ガチエリア": ["classified/02-rule-stage/a.md"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest().save(manifest_path)

    categories = [
        Category(id="02-rule-stage", label="ルール×ステージ", description="定石"),
    ]
    provider = FakeLLMProvider(responses=["## 海女美術 ガチエリア\n\n本文。"])
    stage_cfg = StageConfig(provider="fake", model="x", max_tokens=8192)

    compile_stage.run(
        provider=provider,
        stage_cfg=stage_cfg,
        categories=categories,
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        clusters_path=clusters_path,
        manifest_path=manifest_path,
        prompt_path=workspace / "pipeline" / "prompts" / "compile.md",
        source_urls={"sample_raw/a.md": "https://drive.google.com/file/d/AAA"},
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=workspace,
    )

    out = workspace / "wiki" / "02-rule-stage" / "海女美術-ガチエリア.md"
    assert out.exists()
    fm, body = read_frontmatter(out, WikiFrontmatter)
    assert fm.category == "02-rule-stage"
    assert fm.subtopic == "海女美術-ガチエリア"
    assert fm.sources == ["https://drive.google.com/file/d/AAA"]
    assert "## 海女美術 ガチエリア" in body
    assert "## 出典" in body
    assert "https://drive.google.com/file/d/AAA" in body


def test_compile_skips_unchanged_cluster(workspace: Path) -> None:
    _seed_classified(
        workspace / "classified" / "02-rule-stage" / "a.md",
        "海女美術-ガチエリア",
        "body",
    )
    clusters_path = workspace / "state" / "clusters.json"
    paths = ["classified/02-rule-stage/a.md"]
    clusters_path.write_text(
        json.dumps({"02-rule-stage/海女美術-ガチエリア": paths}, ensure_ascii=False),
        encoding="utf-8",
    )

    fingerprint = hashlib.sha256("\n".join(sorted(paths)).encode()).hexdigest()
    manifest_path = workspace / "state" / "ingest_manifest.json"
    manifest = Manifest(
        wiki={"wiki/02-rule-stage/海女美術-ガチエリア.md": {"cluster_fingerprint": fingerprint}}
    )
    manifest.save(manifest_path)

    provider = FakeLLMProvider(responses=[])
    compile_stage.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1),
        categories=[Category(id="02-rule-stage", label="x", description="y")],
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        clusters_path=clusters_path,
        manifest_path=manifest_path,
        prompt_path=workspace / "pipeline" / "prompts" / "compile.md",
        source_urls={},
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=workspace,
    )

    assert provider.calls == []
