import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
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


def test_consolidate_rewrites_classified_frontmatter_to_new_subtopic(
    workspace: Path,
) -> None:
    cls_path = _seed_classified(
        workspace,
        "01-principles",
        "2026-04-26-dakai-home.md",
        "2026-04-26-general-dakai-home-base-clearing",
    )

    rename = {
        "category": "01-principles",
        "from": "2026-04-26-general-dakai-home-base-clearing",
        "to": "dakai-fundamentals",
        "reason": "打開時の自陣処理は dakai-fundamentals の範疇",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])
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

    fm, _ = read_frontmatter(cls_path, ClassifiedFrontmatter)
    assert fm.subtopic == "dakai-fundamentals"


def test_consolidate_tombstones_old_wiki_page(workspace: Path) -> None:
    _seed_classified(
        workspace,
        "01-principles",
        "2026-04-26-dakai-home.md",
        "2026-04-26-general-dakai-home-base-clearing",
    )
    # Pre-existing wiki page from a prior compile run
    wiki_dir = workspace / "wiki" / "01-principles"
    wiki_dir.mkdir(parents=True)
    old_wiki = wiki_dir / "2026-04-26-general-dakai-home-base-clearing.md"
    old_fm = WikiFrontmatter(
        title="2026-04-26-general-dakai-home-base-clearing",
        category="01-principles",
        subtopic="2026-04-26-general-dakai-home-base-clearing",
        sources=[],
        updated_at=datetime(2026, 4, 26, 12, 0, 0),
    )
    write_frontmatter(old_wiki, old_fm, "## old\n\n古い本文。\n")

    rename = {
        "category": "01-principles",
        "from": "2026-04-26-general-dakai-home-base-clearing",
        "to": "dakai-fundamentals",
        "reason": "打開時の自陣処理は dakai-fundamentals の範疇",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])
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

    assert old_wiki.exists()  # tombstone file still occupies the URL
    fm, body = read_frontmatter(old_wiki, WikiFrontmatter)
    assert fm.tombstone is True
    assert fm.merged_into == "dakai-fundamentals"
    assert fm.merged_at == datetime(2026, 4, 26, 14, 32, 0)
    assert "[dakai-fundamentals](dakai-fundamentals.md)" in body
    assert "打開時の自陣処理は dakai-fundamentals の範疇" in body
    assert "古い本文" not in body  # old content gone


def test_consolidate_skips_tombstone_when_old_wiki_does_not_exist(
    workspace: Path,
) -> None:
    """If the old subtopic was never compiled to wiki yet, no tombstone needed."""
    _seed_classified(
        workspace,
        "01-principles",
        "2026-04-26-dakai-home.md",
        "2026-04-26-general-dakai-home-base-clearing",
    )
    rename = {
        "category": "01-principles",
        "from": "2026-04-26-general-dakai-home-base-clearing",
        "to": "dakai-fundamentals",
        "reason": "範疇内",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])

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

    # No wiki page existed, so no tombstone created. classified subtopic still updated.
    old_slug = "2026-04-26-general-dakai-home-base-clearing.md"
    assert not (workspace / "wiki" / "01-principles" / old_slug).exists()


def test_consolidate_appends_log_entry(workspace: Path) -> None:
    _seed_classified(
        workspace,
        "01-principles",
        "2026-04-26-x.md",
        "2026-04-26-general-x",
    )
    rename = {
        "category": "01-principles",
        "from": "2026-04-26-general-x",
        "to": "x-fundamentals",
        "reason": "汎用 slug に統合",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])
    log_path = workspace / "state" / "consolidate_log.md"

    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=log_path,
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    text = log_path.read_text(encoding="utf-8")
    assert "2026-04-26T14:32:00" in text
    assert "01-principles/2026-04-26-general-x" in text
    assert "01-principles/x-fundamentals" in text
    assert "汎用 slug に統合" in text


def test_consolidate_log_appends_across_runs(workspace: Path) -> None:
    log_path = workspace / "state" / "consolidate_log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("## existing previous entry\n\nfoo\n", encoding="utf-8")

    _seed_classified(workspace, "01-principles", "2026-04-26-y.md", "old-y")
    rename = {
        "category": "01-principles",
        "from": "old-y",
        "to": "new-y",
        "reason": "test",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])

    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=log_path,
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    text = log_path.read_text(encoding="utf-8")
    assert "## existing previous entry" in text  # preserved
    assert "old-y" in text  # new entry appended
