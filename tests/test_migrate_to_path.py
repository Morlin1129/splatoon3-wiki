"""Tests for scripts/migrate_to_path.py.

The script converts legacy frontmatter (with `subtopic`) into the new
path-based schema. It edits files in place by manipulating frontmatter
strings — it does NOT round-trip through the new pydantic models (which
no longer accept `subtopic`).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import frontmatter

from scripts.migrate_to_path import migrate_workspace


def _write_legacy_classified(path: Path, category: str, subtopic: str, body: str = "本文") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "source_file": "sample_raw/x.md",
        "source_date": "2026-04-01",
        "extracted_at": datetime(2026, 4, 1, tzinfo=UTC).isoformat(),
        "content_hash": "h1",
        "category": category,
        "subtopic": subtopic,
    }
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def _write_legacy_wiki(
    path: Path,
    category: str,
    subtopic: str,
    *,
    tombstone: bool = False,
    merged_into: str | None = None,
    body: str = "本文",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata: dict = {
        "title": "x",
        "category": category,
        "subtopic": subtopic,
        "sources": [],
        "updated_at": datetime(2026, 4, 1, tzinfo=UTC).isoformat(),
        "tombstone": tombstone,
    }
    if merged_into is not None:
        metadata["merged_into"] = merged_into
        metadata["merged_at"] = datetime(2026, 4, 1, tzinfo=UTC).isoformat()
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def test_migrates_classified_subtopic_to_path(tmp_path: Path) -> None:
    classified = tmp_path / "classified" / "01-principles" / "x.md"
    _write_legacy_classified(classified, "01-principles", "dakai-fundamentals")
    migrate_workspace(tmp_path)
    post = frontmatter.loads(classified.read_text(encoding="utf-8"))
    assert "subtopic" not in post.metadata
    assert post.metadata["path"] == ["dakai-fundamentals"]


def test_migrates_wiki_subtopic_to_path(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki" / "01-principles" / "dakai-fundamentals.md"
    _write_legacy_wiki(wiki, "01-principles", "dakai-fundamentals")
    migrate_workspace(tmp_path)
    post = frontmatter.loads(wiki.read_text(encoding="utf-8"))
    assert "subtopic" not in post.metadata
    assert post.metadata["path"] == ["dakai-fundamentals"]


def test_migrates_tombstone_merged_into(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki" / "01-principles" / "old-name.md"
    _write_legacy_wiki(
        wiki,
        "01-principles",
        "old-name",
        tombstone=True,
        merged_into="new-name",
    )
    migrate_workspace(tmp_path)
    post = frontmatter.loads(wiki.read_text(encoding="utf-8"))
    assert "merged_into" not in post.metadata
    assert post.metadata["merged_into_path"] == ["new-name"]


def test_migrates_manifest_classified_path(tmp_path: Path) -> None:
    classified = tmp_path / "classified" / "01-principles" / "x.md"
    _write_legacy_classified(classified, "01-principles", "dakai-fundamentals")
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_data = (
        '{"raw": {}, "snippets": {"snippets/x.md": '
        '{"source_hash": "h", "classified": true}}, "wiki": {}}\n'
    )
    manifest_path.write_text(manifest_data, encoding="utf-8")
    migrate_workspace(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "01-principles" in data["known_paths_cache"]
    assert data["known_paths_cache"]["01-principles"] == [["dakai-fundamentals"]]


def test_idempotent_when_already_migrated(tmp_path: Path) -> None:
    classified = tmp_path / "classified" / "01-principles" / "x.md"
    metadata = {
        "source_file": "sample_raw/x.md",
        "source_date": "2026-04-01",
        "extracted_at": datetime(2026, 4, 1, tzinfo=UTC).isoformat(),
        "content_hash": "h1",
        "category": "01-principles",
        "path": ["dakai-fundamentals"],
    }
    classified.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("本文", **metadata)
    classified.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    before = classified.read_text(encoding="utf-8")
    migrate_workspace(tmp_path)
    after = classified.read_text(encoding="utf-8")
    assert before == after  # no-op on already-migrated files
