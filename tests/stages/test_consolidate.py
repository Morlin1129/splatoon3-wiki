import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import StageConfig
from pipeline.frontmatter_io import write_frontmatter
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
    workspace: Path, category: str, name: str, subtopic: str, body: str = "本文"
) -> Path:
    path = workspace / "classified" / category / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
        category=category,
        subtopic=subtopic,
    )
    write_frontmatter(path, fm, body)
    return path


def test_consolidate_no_op_when_no_classified_files(workspace: Path) -> None:
    provider = FakeLLMProvider(responses=[])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )
    assert provider.calls == []
    assert not (workspace / "state" / "consolidate_log.md").exists()


def test_consolidate_no_changes_when_llm_returns_empty_renames(workspace: Path) -> None:
    classified_path = _seed_classified(
        workspace, "01-principles", "2026-04-26-x.md", "dakai-fundamentals"
    )
    original = classified_path.read_text(encoding="utf-8")

    provider = FakeLLMProvider(responses=[json.dumps({"renames": []})])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    assert len(provider.calls) == 1
    # category id and subtopic must be in the user prompt
    assert "01-principles" in provider.calls[0].user
    assert "dakai-fundamentals" in provider.calls[0].user
    # No file changes
    assert classified_path.read_text(encoding="utf-8") == original
    assert not (workspace / "state" / "consolidate_log.md").exists()
