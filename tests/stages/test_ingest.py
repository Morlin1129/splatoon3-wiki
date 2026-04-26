import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import StageConfig
from pipeline.frontmatter_io import read_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import SnippetFrontmatter
from pipeline.stages import ingest
from pipeline.state import Manifest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "sample_raw").mkdir()
    (tmp_path / "snippets").mkdir()
    (tmp_path / "state").mkdir()
    return tmp_path


def test_ingest_creates_snippet_files(workspace: Path) -> None:
    raw = workspace / "sample_raw" / "2026-04-01-notes.md"
    raw.write_text("# Notes\n\n右高台の制圧は…", encoding="utf-8")

    llm_response = json.dumps(
        [
            {"slug": "right-high-control", "content": "右高台の制圧はリスクあり。"},
            {"slug": "two-down-retreat", "content": "2 落ちしたら退く。"},
        ],
        ensure_ascii=False,
    )
    provider = FakeLLMProvider(responses=[llm_response])

    stage_cfg = StageConfig(provider="fake", model="x", max_tokens=4096)
    ingest.run(
        provider=provider,
        stage_cfg=stage_cfg,
        raw_dir=workspace / "sample_raw",
        snippets_dir=workspace / "snippets",
        manifest_path=workspace / "state" / "ingest_manifest.json",
        system_prompt="INGEST PROMPT",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
    )

    snippets = sorted((workspace / "snippets").glob("*.md"))
    assert len(snippets) == 2

    fm, body = read_frontmatter(snippets[0], SnippetFrontmatter)
    assert fm.source_file.endswith("2026-04-01-notes.md")
    assert fm.source_date == "2026-04-01"
    assert fm.extracted_at == datetime(2026, 4, 24, 12, 0, 0)
    assert body.strip() in {"右高台の制圧はリスクあり。", "2 落ちしたら退く。"}


def test_ingest_skips_unchanged_raw(workspace: Path) -> None:
    raw = workspace / "sample_raw" / "2026-04-01-notes.md"
    raw.write_text("# Notes", encoding="utf-8")

    manifest_path = workspace / "state" / "ingest_manifest.json"
    import hashlib

    h = hashlib.sha256(raw.read_bytes()).hexdigest()
    manifest = Manifest(raw={str(raw.relative_to(workspace)): {"content_hash": h}})
    manifest.save(manifest_path)

    provider = FakeLLMProvider(responses=[])  # will assert if called

    stage_cfg = StageConfig(provider="fake", model="x", max_tokens=4096)
    ingest.run(
        provider=provider,
        stage_cfg=stage_cfg,
        raw_dir=workspace / "sample_raw",
        snippets_dir=workspace / "snippets",
        manifest_path=manifest_path,
        system_prompt="INGEST PROMPT",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=workspace,
    )

    assert provider.calls == []  # no LLM call since nothing changed
    assert list((workspace / "snippets").glob("*.md")) == []
