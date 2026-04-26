from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.config import StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _collect_subtopics(classified_dir: Path) -> dict[str, dict[str, int]]:
    """Return {category_id: {subtopic: snippet_count}} for non-empty categories."""
    by_cat: dict[str, dict[str, int]] = {}
    for cat_dir in sorted(classified_dir.glob("*/")):
        cat_id = cat_dir.name
        counts: dict[str, int] = {}
        for path in sorted(cat_dir.glob("*.md")):
            fm, _ = read_frontmatter(path, ClassifiedFrontmatter)
            if fm is None:
                raise RuntimeError(f"unreachable: classified missing frontmatter: {path}")
            counts[fm.subtopic] = counts.get(fm.subtopic, 0) + 1
        if counts:
            by_cat[cat_id] = counts
    return by_cat


def _build_user_prompt(category_id: str, subtopics: dict[str, int]) -> str:
    lines = [f"カテゴリ: {category_id}", "", "現在の subtopic 一覧 (snippet 数):"]
    for subtopic, count in sorted(subtopics.items()):
        lines.append(f"- {subtopic}: {count}")
    return "\n".join(lines)


def _rewrite_classified_subtopic(classified_dir: Path, category: str, src: str, dst: str) -> None:
    cat_dir = classified_dir / category
    for path in sorted(cat_dir.glob("*.md")):
        fm, body = read_frontmatter(path, ClassifiedFrontmatter)
        if fm is None or fm.subtopic != src:
            continue
        new_fm = ClassifiedFrontmatter(**{**fm.model_dump(), "subtopic": dst})
        write_frontmatter(path, new_fm, body)


def _tombstone_wiki_page(
    wiki_dir: Path, category: str, src: str, dst: str, reason: str, now: datetime
) -> None:
    old_wiki = wiki_dir / category / f"{src}.md"
    if not old_wiki.exists():
        return  # nothing was ever compiled for this subtopic; no URL to preserve
    tombstone_fm = WikiFrontmatter(
        title=f"統合済み: {src}",
        category=category,
        subtopic=src,
        sources=[],
        updated_at=now,
        tombstone=True,
        merged_into=dst,
        merged_at=now,
    )
    body_lines = [
        f"# 統合済み: {src}",
        "",
        f"このページは [{dst}]({dst}.md) に統合されました。",
    ]
    if reason:
        body_lines.append("")
        body_lines.append(f"統合理由: {reason}")
    write_frontmatter(old_wiki, tombstone_fm, "\n".join(body_lines) + "\n")


def _append_log(log_path: Path, renames: list[dict[str, Any]], now: datetime) -> None:
    if not renames:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"## {now.isoformat()}",
        "",
        f"{len(renames)} 件の subtopic を統合した。",
        "",
    ]
    for r in renames:
        cat, src, dst = r["category"], r["from"], r["to"]
        lines.append(f"- `{cat}/{src}` → `{cat}/{dst}`")
        reason = r.get("reason")
        if reason:
            lines.append(f"  - 理由: {reason}")
    lines.append("")
    lines.append("---")
    lines.append("")
    new_block = "\n".join(lines)
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(existing + new_block, encoding="utf-8")


def _validate_rename(rename: dict[str, Any], available: dict[str, dict[str, int]]) -> None:
    cat = rename.get("category")
    src = rename.get("from")
    dst = rename.get("to")
    if not isinstance(cat, str) or not isinstance(src, str) or not isinstance(dst, str):
        raise ValueError(f"consolidate: malformed rename entry: {rename!r}")
    if cat not in available:
        raise ValueError(f"consolidate: unknown category in rename: {cat!r}")
    if src not in available[cat]:
        raise ValueError(f"consolidate: unknown source subtopic in rename: {cat}/{src}")


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    classified_dir: Path,
    wiki_dir: Path,
    log_path: Path,
    system_prompt: str,
    now: Callable[[], datetime] = _now_utc,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    debug_dir = root / "state" / "debug"

    by_cat = _collect_subtopics(classified_dir)
    if not by_cat:
        return

    all_renames: list[dict[str, Any]] = []
    for cat_id, subtopics in by_cat.items():
        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(cat_id, subtopics),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="consolidate", debug_dir=debug_dir)
        all_renames.extend(parsed.get("renames", []))

    if not all_renames:
        return

    for r in all_renames:
        _validate_rename(r, by_cat)

    ts = now()
    for r in all_renames:
        cat = r["category"]
        src = r["from"]
        dst = r["to"]
        reason = r.get("reason", "")
        _rewrite_classified_subtopic(classified_dir, cat, src, dst)
        _tombstone_wiki_page(wiki_dir, cat, src, dst, reason, ts)
    _append_log(log_path, all_renames, ts)
