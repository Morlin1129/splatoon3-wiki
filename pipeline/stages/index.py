from __future__ import annotations

from pathlib import Path

from pipeline.config import Category
from pipeline.frontmatter_io import read_frontmatter
from pipeline.models import WikiFrontmatter


_NO_BODY = "(本文なし)"
_PARAGRAPH_BREAK_PREFIXES = ("#", "-", "*", ">", "|", "```")
_SUMMARY_MAX_CHARS = 120


def _extract_summary(body: str) -> str:
    """Return the first sentence of the first non-heading paragraph.

    Falls back to "(本文なし)" if no eligible paragraph is found.
    Sentences end on a Japanese full stop `。` or an ASCII `.` followed by
    whitespace or end-of-string. The result is truncated to 120 Unicode
    code points with "…" appended when the source sentence is longer.
    """
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


def _list_pages(cat_dir: Path) -> list[Path]:
    if not cat_dir.is_dir():
        return []
    return sorted(p for p in cat_dir.glob("*.md") if p.name != "README.md")


def _write_category_readme(cat: Category, cat_dir: Path, pages: list[Path]) -> None:
    lines = [f"# {cat.id} — {cat.label}", "", cat.description, "", "## ページ一覧", ""]
    if not pages:
        lines.append("(まだページがありません)")
    else:
        for page_path in pages:
            fm, body = read_frontmatter(page_path, WikiFrontmatter)
            if fm is None:
                raise RuntimeError(f"unreachable: wiki page missing frontmatter: {page_path}")
            summary = _extract_summary(body)
            lines.append(f"- [{fm.title}]({page_path.name}) — {summary}")
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    """Generate wiki/README.md and per-category README.md files."""
    counts: dict[str, int] = {}
    for cat in categories:
        cat_dir = wiki_dir / cat.id
        pages = _list_pages(cat_dir)
        counts[cat.id] = len(pages)
        _write_category_readme(cat, cat_dir, pages)
    _write_top_readme(wiki_dir, categories, counts)
