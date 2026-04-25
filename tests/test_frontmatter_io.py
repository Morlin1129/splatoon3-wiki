from datetime import datetime
from pathlib import Path

from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.models import SnippetFrontmatter


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    fm = SnippetFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="hash_123",
    )
    target = tmp_path / "snippet.md"
    body = "右高台の制圧は味方の復帰を遅らせるリスクがある。"

    write_frontmatter(target, fm, body)

    loaded_fm, loaded_body = read_frontmatter(target, SnippetFrontmatter)
    assert loaded_fm == fm
    assert loaded_body.strip() == body


def test_read_plain_markdown_without_frontmatter(tmp_path: Path) -> None:
    target = tmp_path / "plain.md"
    target.write_text("# Just body\n\nNo frontmatter.\n", encoding="utf-8")

    _, body = read_frontmatter(target, SnippetFrontmatter, require=False)

    assert body.strip().startswith("# Just body")
