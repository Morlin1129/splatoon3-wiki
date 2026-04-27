from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category
from pipeline.frontmatter_io import write_frontmatter
from pipeline.models import WikiFrontmatter
from pipeline.stages import index as index_stage
from pipeline.stages.index import _extract_summary


def test_extract_summary_takes_first_sentence_after_title() -> None:
    body = "## タイトル\n\n最初の文。続きの文。\n\n## 別セクション\n"
    assert _extract_summary(body) == "最初の文。"


def test_extract_summary_handles_ascii_period() -> None:
    body = "## Title\n\nFirst sentence. Second sentence.\n"
    assert _extract_summary(body) == "First sentence."


def test_extract_summary_truncates_long_sentence() -> None:
    long_sentence = "あ" * 130 + "。"
    body = f"## タイトル\n\n{long_sentence}\n"
    result = _extract_summary(body)
    assert result.endswith("…")
    assert len(result) == 121


def test_extract_summary_returns_placeholder_when_body_empty() -> None:
    body = "## タイトル\n\n"
    assert _extract_summary(body) == "(本文なし)"


def test_extract_summary_skips_bullet_lines() -> None:
    body = "## タイトル\n\n- 箇条書きはサマリにしない\n- 二つ目\n\n通常段落。\n"
    assert _extract_summary(body) == "通常段落。"


def test_extract_summary_works_without_heading() -> None:
    body = "見出しなしの段落。続き。\n"
    assert _extract_summary(body) == "見出しなしの段落。"


def _write_wiki(path: Path, *, title: str, subtopic: str, body: str) -> None:
    fm = WikiFrontmatter(
        title=title,
        category=path.parent.name,
        subtopic=subtopic,
        sources=[],
        updated_at=datetime(2026, 4, 24, 12, 0, 0),
    )
    write_frontmatter(path, fm, body)


def _write_tombstone_wiki(path: Path, *, subtopic: str, merged_into: str) -> None:
    fm = WikiFrontmatter(
        title=f"統合済み: {subtopic}",
        category=path.parent.name,
        subtopic=subtopic,
        sources=[],
        updated_at=datetime(2026, 4, 26, 14, 32, 0),
        tombstone=True,
        merged_into=merged_into,
        merged_at=datetime(2026, 4, 26, 14, 32, 0),
    )
    body = (
        f"# 統合済み: {subtopic}\n\n"
        f"このページは [{merged_into}]({merged_into}.md) に統合されました。\n"
    )
    write_frontmatter(path, fm, body)


@pytest.fixture
def categories() -> list[Category]:
    return [
        Category(id="01-principles", label="原理原則", description="普遍理論"),
        Category(id="02-rule-stage", label="ルール×ステージ", description="定石"),
        Category(id="03-weapon-role", label="ブキ・役割", description="ブキ別ノウハウ"),
    ]


def test_index_uses_frontmatter_title_not_body_heading(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "01-principles").mkdir(parents=True)

    _write_wiki(
        wiki_dir / "01-principles" / "page.md",
        title="人数不利時の退避方針",
        subtopic="two-down-retreat",
        body="## 別の見出し\n\n本文。\n",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    cat1 = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")
    assert "[人数不利時の退避方針](page.md)" in cat1
    assert "別の見出し" not in cat1


def test_index_writes_top_level_and_per_category(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "01-principles").mkdir(parents=True)
    (wiki_dir / "02-rule-stage").mkdir(parents=True)
    # 03-weapon-role intentionally absent

    _write_wiki(
        wiki_dir / "01-principles" / "two-down-retreat.md",
        title="2 落ち時の退避",
        subtopic="two-down-retreat",
        body="## 2 落ち時の退避\n\n人数不利時はオブジェクト関与より復帰を優先する。\n",
    )
    _write_wiki(
        wiki_dir / "01-principles" / "hate-management.md",
        title="ヘイト管理",
        subtopic="hate-management",
        body="## ヘイト管理\n\n誰が敵の視線を集めるか役割分担する。\n",
    )
    _write_wiki(
        wiki_dir / "02-rule-stage" / "amabi-right-high.md",
        title="海女美術 右高台",
        subtopic="amabi-right-high",
        body="## 海女美術 右高台\n\n右高台はリスクと裏取り誘発を伴う。\n",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    assert "# Splatoon 3 Wiki" in top
    assert "[01-principles](01-principles/) — 原理原則 — 2 ページ" in top
    assert "[02-rule-stage](02-rule-stage/) — ルール×ステージ — 1 ページ" in top
    assert "[03-weapon-role](03-weapon-role/) — ブキ・役割 — 0 ページ" in top

    cat1 = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")
    assert "# 01-principles — 原理原則" in cat1
    assert "普遍理論" in cat1
    assert cat1.index("hate-management.md") < cat1.index("two-down-retreat.md")
    assert "[ヘイト管理](hate-management.md) — 誰が敵の視線を集めるか役割分担する。" in cat1
    assert (
        "[2 落ち時の退避](two-down-retreat.md) — 人数不利時はオブジェクト関与より復帰を優先する。"
        in cat1
    )

    cat3 = (wiki_dir / "03-weapon-role" / "README.md").read_text(encoding="utf-8")
    assert "(まだページがありません)" in cat3


def test_index_skips_existing_readme_when_counting_and_listing(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    cat_dir = wiki_dir / "01-principles"
    cat_dir.mkdir(parents=True)

    _write_wiki(
        cat_dir / "page-one.md",
        title="ページ1",
        subtopic="page-one",
        body="## ページ1\n\n本文。\n",
    )
    (cat_dir / "README.md").write_text("# stale", encoding="utf-8")

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    assert "01-principles](01-principles/) — 原理原則 — 1 ページ" in top

    cat1 = (cat_dir / "README.md").read_text(encoding="utf-8")
    assert "page-one" in cat1
    assert "stale" not in cat1


def test_index_is_idempotent(tmp_path: Path, categories: list[Category]) -> None:
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "01-principles").mkdir(parents=True)
    _write_wiki(
        wiki_dir / "01-principles" / "p.md",
        title="P",
        subtopic="p",
        body="## P\n\n本文。\n",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)
    first_top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    first_cat = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")

    index_stage.run(wiki_dir=wiki_dir, categories=categories)
    second_top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    second_cat = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")

    assert first_top == second_top
    assert first_cat == second_cat


def test_index_excludes_tombstones_from_category_listing(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    cat_dir = wiki_dir / "01-principles"
    cat_dir.mkdir(parents=True)

    _write_wiki(
        cat_dir / "live-page.md",
        title="生きているページ",
        subtopic="live-page",
        body="## 生きているページ\n\n本文。\n",
    )
    _write_tombstone_wiki(
        cat_dir / "old-page.md",
        subtopic="old-page",
        merged_into="live-page",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    cat_readme = (cat_dir / "README.md").read_text(encoding="utf-8")
    assert "[生きているページ](live-page.md)" in cat_readme
    assert "old-page.md" not in cat_readme  # tombstone hidden
    assert "統合済み" not in cat_readme


def test_index_excludes_tombstones_from_top_level_count(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    cat_dir = wiki_dir / "01-principles"
    cat_dir.mkdir(parents=True)

    _write_wiki(
        cat_dir / "live.md",
        title="ライブ",
        subtopic="live",
        body="## ライブ\n\n本文。\n",
    )
    _write_tombstone_wiki(
        cat_dir / "tombstone.md",
        subtopic="tombstone",
        merged_into="live",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    assert "01-principles](01-principles/) — 原理原則 — 1 ページ" in top
