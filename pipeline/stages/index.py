from __future__ import annotations

from pathlib import Path

from pipeline.config import Category, FixedLevel
from pipeline.frontmatter_io import read_frontmatter
from pipeline.models import WikiFrontmatter

_NO_BODY = "(本文なし)"
_PARAGRAPH_BREAK_PREFIXES = ("#", "-", "*", ">", "|", "```")
_SUMMARY_MAX_CHARS = 120


def _extract_summary(body: str) -> str:
    lines = body.splitlines()
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("## ", "# ")):
            start = i + 1
            break

    paragraph_lines: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(_PARAGRAPH_BREAK_PREFIXES):
            if paragraph_lines:
                break
            continue
        paragraph_lines.append(stripped)

    if not paragraph_lines:
        return _NO_BODY

    paragraph = " ".join(paragraph_lines)
    sentence = paragraph
    for idx, ch in enumerate(paragraph):
        if ch == "。":
            sentence = paragraph[: idx + 1]
            break
        if ch == "." and (idx + 1 >= len(paragraph) or paragraph[idx + 1].isspace()):
            sentence = paragraph[: idx + 1]
            break

    if len(sentence) > _SUMMARY_MAX_CHARS:
        sentence = sentence[:_SUMMARY_MAX_CHARS] + "…"
    return sentence


def _is_excluded(p: Path) -> bool:
    """README.md is excluded; tombstone leaves are excluded."""
    if p.name == "README.md":
        return True
    fm, _ = read_frontmatter(p, WikiFrontmatter, require=False)
    if fm is not None and fm.tombstone:
        return True
    return False


def _list_subdirectories(d: Path) -> list[Path]:
    return sorted([p for p in d.iterdir() if p.is_dir()])


def _list_leaf_pages(d: Path) -> list[Path]:
    return sorted([p for p in d.glob("*.md") if not _is_excluded(p)])


def _label_at_level(level: FixedLevel, parent_id: str | None, value_id: str) -> str | None:
    """Look up the human label for a value id at the given fixed level.

    Returns None if the level is not enumerated, or the value_id isn't listed
    in the level's values / values_by_parent (e.g. it's a free-tail component).
    """
    if level.values is not None:
        for v in level.values:
            if v.id == value_id:
                return v.label
        return None
    if level.values_by_parent is not None and parent_id is not None:
        for v in level.values_by_parent.get(parent_id, []):
            if v.id == value_id:
                return v.label
        return None
    return None


def _resolve_label(category: Category, breadcrumb_ids: list[str], depth: int) -> str:
    """Resolve display label for the directory at `breadcrumb_ids[depth]`.

    Falls back to the raw id when the level is `open` or beyond `fixed_levels`,
    or when the id isn't in the enumerated values.
    """
    value_id = breadcrumb_ids[depth]
    if depth < len(category.fixed_levels):
        level = category.fixed_levels[depth]
        if level.mode == "enumerated":
            parent_id = breadcrumb_ids[depth - 1] if depth > 0 else None
            label = _label_at_level(level, parent_id, value_id)
            if label is not None:
                return label
    return value_id


def _resolve_breadcrumb_labels(category: Category, breadcrumb_ids: list[str]) -> list[str]:
    return [_resolve_label(category, breadcrumb_ids, i) for i in range(len(breadcrumb_ids))]


def _write_intermediate_readme(
    dir_path: Path,
    breadcrumb_ids: list[str],
    breadcrumb_labels: list[str],
    category: Category,
) -> None:
    """Write a static index README for an intermediate node."""
    title = breadcrumb_labels[-1] if breadcrumb_labels else category.label
    if breadcrumb_labels:
        crumb = " > ".join(breadcrumb_labels)
        breadcrumb_line = f"`{category.label} > {crumb}`"
    else:
        breadcrumb_line = f"`{category.label}`"
    lines = [f"# {title}", "", breadcrumb_line, ""]

    subdirs = _list_subdirectories(dir_path)
    if subdirs:
        lines.append("## サブカテゴリ")
        lines.append("")
        sub_depth = len(breadcrumb_ids)
        for sub in subdirs:
            sub_label = _resolve_label(category, [*breadcrumb_ids, sub.name], sub_depth)
            lines.append(f"- [{sub_label}]({sub.name}/)")
        lines.append("")

    leaves = _list_leaf_pages(dir_path)
    if leaves:
        lines.append("## ページ")
        lines.append("")
        for leaf in leaves:
            fm, body = read_frontmatter(leaf, WikiFrontmatter)
            if fm is None:
                continue
            summary = _extract_summary(body)
            lines.append(f"- [{fm.title}]({leaf.name}) — {summary}")
        lines.append("")

    if not subdirs and not leaves:
        lines.append("(まだページがありません)")
        lines.append("")

    (dir_path / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _write_recursive(dir_path: Path, breadcrumb_ids: list[str], category: Category) -> None:
    if not dir_path.is_dir():
        return
    breadcrumb_labels = _resolve_breadcrumb_labels(category, breadcrumb_ids)
    _write_intermediate_readme(dir_path, breadcrumb_ids, breadcrumb_labels, category)
    for sub in _list_subdirectories(dir_path):
        _write_recursive(sub, [*breadcrumb_ids, sub.name], category)


def _count_leaf_pages_recursive(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    count = len(_list_leaf_pages(dir_path))
    for sub in _list_subdirectories(dir_path):
        count += _count_leaf_pages_recursive(sub)
    return count


def _write_top_readme(wiki_dir: Path, categories: list[Category], counts: dict[str, int]) -> None:
    lines = [
        "# Splatoon 3 Wiki",
        "",
        "LLM が生成・編纂したナレッジ集。",
        "",
        "## カテゴリ",
        "",
    ]
    for cat in categories:
        count = counts.get(cat.id, 0)
        lines.append(f"- [{cat.id}]({cat.id}/) — {cat.label} — {count} ページ")
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(*, wiki_dir: Path, categories: list[Category]) -> None:
    """Generate static README.md at every wiki tree node (top, category, intermediates)."""
    counts: dict[str, int] = {}
    for cat in categories:
        cat_dir = wiki_dir / cat.id
        counts[cat.id] = _count_leaf_pages_recursive(cat_dir)
        _write_recursive(cat_dir, [], cat)
    _write_top_readme(wiki_dir, categories, counts)
