from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import Category, FixedLevel, LevelValue
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


def test_index_uses_enumerated_labels_in_titles_and_breadcrumbs(tmp_path: Path) -> None:
    """When fixed_levels are enumerated, the README must display labels (not ids)
    in the title, breadcrumb, and subcategory link text. URLs/dirs keep ids."""
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(
        wiki_dir,
        "03-weapon-role",
        ["shooter", "kelvin-525", "spacing-and-range-management"],
        title="ケルビン525のレンジ管理",
    )
    cats = [
        Category(
            id="03-weapon-role",
            label="ブキ・役割",
            description="x",
            fixed_levels=[
                FixedLevel(
                    name="ブキ種別",
                    mode="enumerated",
                    values=[LevelValue(id="shooter", label="シューター")],
                ),
                FixedLevel(
                    name="個別ブキ",
                    mode="enumerated",
                    values_by_parent={
                        "shooter": [LevelValue(id="kelvin-525", label="ケルビン525")]
                    },
                ),
            ],
        )
    ]
    index.run(wiki_dir=wiki_dir, categories=cats)

    # Top-level category README at <cat>/README.md: subcategory shows label
    cat_readme = (wiki_dir / "03-weapon-role" / "README.md").read_text(encoding="utf-8")
    assert "[シューター](shooter/)" in cat_readme

    # 1st-level intermediate README: title + breadcrumb use label
    shooter_readme = (wiki_dir / "03-weapon-role" / "shooter" / "README.md").read_text(
        encoding="utf-8"
    )
    assert shooter_readme.startswith("# シューター\n")
    assert "ブキ・役割 > シューター" in shooter_readme
    # subcategory link text is label, URL stays as id
    assert "[ケルビン525](kelvin-525/)" in shooter_readme

    # 2nd-level intermediate README: full breadcrumb in labels
    weapon_readme = (
        wiki_dir / "03-weapon-role" / "shooter" / "kelvin-525" / "README.md"
    ).read_text(encoding="utf-8")
    assert weapon_readme.startswith("# ケルビン525\n")
    assert "ブキ・役割 > シューター > ケルビン525" in weapon_readme
    # The page link text is the WikiFrontmatter title, not the slug
    assert "[ケルビン525のレンジ管理](spacing-and-range-management.md)" in weapon_readme


def test_index_falls_back_to_dir_name_for_open_or_free_tail(tmp_path: Path) -> None:
    """Open layers and free-tail components have no enumerated label; the dir
    name is shown as-is in subcategory link text and breadcrumbs."""
    wiki_dir = tmp_path / "wiki"
    # Path is 4 deep: 2 enumerated + 1 free-tail dir + 1 leaf file.
    _seed_wiki(
        wiki_dir,
        "03-weapon-role",
        ["shooter", "kelvin-525", "gear-builds", "kasaratzukaikore"],
    )
    cats = [
        Category(
            id="03-weapon-role",
            label="ブキ",
            description="x",
            fixed_levels=[
                FixedLevel(
                    name="ブキ種別",
                    mode="enumerated",
                    values=[LevelValue(id="shooter", label="シューター")],
                ),
                FixedLevel(
                    name="個別ブキ",
                    mode="enumerated",
                    values_by_parent={
                        "shooter": [LevelValue(id="kelvin-525", label="ケルビン525")]
                    },
                ),
            ],
        )
    ]
    index.run(wiki_dir=wiki_dir, categories=cats)

    # The kelvin-525 README links to its sub-dir "gear-builds" (free tail) by raw name.
    weapon_readme = (
        wiki_dir / "03-weapon-role" / "shooter" / "kelvin-525" / "README.md"
    ).read_text(encoding="utf-8")
    assert "[gear-builds](gear-builds/)" in weapon_readme

    # The README inside gear-builds/ uses the raw dir name in title and breadcrumb.
    free_tail_readme = (
        wiki_dir / "03-weapon-role" / "shooter" / "kelvin-525" / "gear-builds" / "README.md"
    ).read_text(encoding="utf-8")
    assert free_tail_readme.startswith("# gear-builds\n")
    assert "ブキ > シューター > ケルビン525 > gear-builds" in free_tail_readme
