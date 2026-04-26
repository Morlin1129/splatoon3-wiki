from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import StageConfig
from pipeline.frontmatter_io import read_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter


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

    for cat_id, subtopics in by_cat.items():
        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(cat_id, subtopics),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="consolidate", debug_dir=debug_dir)
        renames = parsed.get("renames", [])
        if renames:
            # Renaming is implemented in a later task; for now this branch is
            # intentionally unreachable in tests (Task 5 only covers the empty-
            # renames path). Task 6 replaces this with real apply logic.
            raise NotImplementedError("consolidate rename application not yet implemented")
