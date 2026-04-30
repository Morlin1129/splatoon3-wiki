from datetime import UTC, datetime

import pytest

from pipeline.models import (
    ClassifiedFrontmatter,
    SnippetFrontmatter,
    WikiFrontmatter,
)


def test_classified_frontmatter_with_single_path() -> None:
    fm = ClassifiedFrontmatter(
        source_file="x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 1, tzinfo=UTC),
        content_hash="h1",
        category="01-principles",
        path=["dakai-fundamentals"],
    )
    assert fm.path == ["dakai-fundamentals"]


def test_classified_frontmatter_with_multi_level_path() -> None:
    fm = ClassifiedFrontmatter(
        source_file="x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 1, tzinfo=UTC),
        content_hash="h1",
        category="03-weapon-role",
        path=["シューター", "スプラシューター", "ギア構成"],
    )
    assert len(fm.path) == 3


def test_classified_frontmatter_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="path"):
        ClassifiedFrontmatter(
            source_file="x.md",
            source_date="2026-04-01",
            extracted_at=datetime(2026, 4, 1, tzinfo=UTC),
            content_hash="h1",
            category="01-principles",
            path=[],
        )


def test_classified_frontmatter_rejects_path_component_with_slash() -> None:
    with pytest.raises(ValueError, match="must not contain"):
        ClassifiedFrontmatter(
            source_file="x.md",
            source_date="2026-04-01",
            extracted_at=datetime(2026, 4, 1, tzinfo=UTC),
            content_hash="h1",
            category="01-principles",
            path=["bad/component"],
        )


def test_wiki_frontmatter_with_path_and_merged_into() -> None:
    fm = WikiFrontmatter(
        title="x",
        category="01-principles",
        path=["dakai-fundamentals"],
        sources=[],
        updated_at=datetime(2026, 4, 1, tzinfo=UTC),
        tombstone=True,
        merged_into_path=["dakai-principles"],
        merged_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert fm.merged_into_path == ["dakai-principles"]


def test_wiki_frontmatter_default_merged_into_is_none() -> None:
    fm = WikiFrontmatter(
        title="x",
        category="01-principles",
        path=["x"],
        sources=[],
        updated_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert fm.merged_into_path is None
    assert fm.tombstone is False


def test_snippet_frontmatter_basic() -> None:
    fm = SnippetFrontmatter(
        source_file="x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 1, tzinfo=UTC),
        content_hash="h1",
    )
    assert fm.source_file == "x.md"
