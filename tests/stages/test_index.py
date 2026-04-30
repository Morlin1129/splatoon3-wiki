from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import Category
from pipeline.frontmatter_io import write_frontmatter
from pipeline.models import WikiFrontmatter
from pipeline.stages import index


def _seed_wiki(
    wiki_dir: Path,
    category: str,
    path: list[str],
    *,
    title: str = "ページタイトル",
    body: str = "概要文。",
    tombstone: bool = False,
) -> Path:
    out = wiki_dir / category / Path(*path).with_suffix(".md")
    fm = WikiFrontmatter(
        title=title,
        category=category,
        path=path,
        sources=[],
        updated_at=datetime(2026, 4, 30, tzinfo=UTC),
        tombstone=tombstone,
    )
    write_frontmatter(out, fm, body)
    return out


def test_index_writes_top_readme(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(wiki_dir, "01-principles", ["dakai-fundamentals"])
    cats = [Category(id="01-principles", label="原理原則", description="x")]
    index.run(wiki_dir=wiki_dir, categories=cats)
    top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    assert "01-principles" in top


def test_index_writes_intermediate_readme_for_multi_level(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(wiki_dir, "03-weapon-role", ["シューター", "スプラシューター", "ギア構成"])
    _seed_wiki(wiki_dir, "03-weapon-role", ["シューター", "ボールドマーカー", "立ち回り"])
    cats = [Category(id="03-weapon-role", label="ブキ", description="x")]
    index.run(wiki_dir=wiki_dir, categories=cats)

    shooter_readme = (wiki_dir / "03-weapon-role" / "シューター" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "スプラシューター" in shooter_readme
    assert "ボールドマーカー" in shooter_readme

    splash_readme = (
        wiki_dir / "03-weapon-role" / "シューター" / "スプラシューター" / "README.md"
    ).read_text(encoding="utf-8")
    assert "ギア構成" in splash_readme


def test_index_excludes_tombstones_from_listing(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(wiki_dir, "01-principles", ["alive-page"])
    _seed_wiki(wiki_dir, "01-principles", ["dead-page"], tombstone=True)
    cats = [Category(id="01-principles", label="原理原則", description="x")]
    index.run(wiki_dir=wiki_dir, categories=cats)
    cat_readme = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")
    assert "alive-page" in cat_readme
    assert "dead-page" not in cat_readme


def test_index_no_args_other_than_wiki_and_categories(tmp_path: Path) -> None:
    """Sanity: index ステージは LLM を一切呼ばない（provider 引数なし）。"""
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(wiki_dir, "01-principles", ["x"])
    index.run(
        wiki_dir=wiki_dir,
        categories=[Category(id="01-principles", label="y", description="z")],
    )
