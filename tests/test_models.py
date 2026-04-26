from datetime import datetime

import pytest
from pydantic import ValidationError

from pipeline.models import ClassifiedFrontmatter, SnippetFrontmatter, WikiFrontmatter


def test_snippet_frontmatter_minimum_fields() -> None:
    fm = SnippetFrontmatter(
        source_file="sample_raw/2026-04-01-meeting-notes.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="abc123",
    )

    assert fm.source_file.endswith(".md")
    assert fm.content_hash == "abc123"


def test_classified_frontmatter_requires_category_and_subtopic() -> None:
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="abc123",
        category="02-rule-stage",
        subtopic="海女美術_ガチエリア",
    )

    assert fm.category == "02-rule-stage"

    with pytest.raises(ValidationError):
        ClassifiedFrontmatter(
            source_file="x.md",
            source_date="2026-04-01",
            extracted_at=datetime(2026, 4, 24, 12, 0, 0),
            content_hash="abc123",
            category="",  # empty rejected
            subtopic="x",
        )


def test_wiki_frontmatter_sources_list() -> None:
    fm = WikiFrontmatter(
        title="海女美術 ガチエリア定石",
        category="02-rule-stage",
        subtopic="海女美術_ガチエリア",
        sources=[
            "https://drive.google.com/file/d/AAA",
            "https://drive.google.com/file/d/BBB",
        ],
        updated_at=datetime(2026, 4, 24, 12, 0, 0),
    )

    assert len(fm.sources) == 2
    assert fm.title == "海女美術 ガチエリア定石"


def test_wiki_frontmatter_requires_non_empty_title() -> None:
    with pytest.raises(ValidationError):
        WikiFrontmatter(
            title="",
            category="02-rule-stage",
            subtopic="海女美術_ガチエリア",
            sources=[],
            updated_at=datetime(2026, 4, 24, 12, 0, 0),
        )

    with pytest.raises(ValidationError):
        WikiFrontmatter(  # type: ignore[call-arg]
            category="02-rule-stage",
            subtopic="海女美術_ガチエリア",
            sources=[],
            updated_at=datetime(2026, 4, 24, 12, 0, 0),
        )
