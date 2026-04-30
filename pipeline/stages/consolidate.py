from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.config import Category, FixedLevel, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.state import Manifest


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _collect_path_frequencies(
    classified_dir: Path,
) -> dict[str, dict[tuple[str, ...], int]]:
    """Return {category_id: {path_tuple: snippet_count}} for non-empty categories."""
    by_cat: dict[str, dict[tuple[str, ...], int]] = {}
    for cat_dir in sorted(classified_dir.glob("*/")):
        cat_id = cat_dir.name
        counts: dict[tuple[str, ...], int] = {}
        for path in sorted(cat_dir.glob("*.md")):
            fm, _ = read_frontmatter(path, ClassifiedFrontmatter)
            if fm is None:
                raise RuntimeError(f"unreachable: classified missing frontmatter: {path}")
            key = tuple(fm.path)
            counts[key] = counts.get(key, 0) + 1
        if counts:
            by_cat[cat_id] = counts
    return by_cat


def _hash_frequency_map(freq_map: dict[tuple[str, ...], int]) -> str:
    canonical = sorted((list(p), c) for p, c in freq_map.items())
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False).encode("utf-8")).hexdigest()


def _has_free_tail(category: Category, freq_map: dict[tuple[str, ...], int]) -> bool:
    """True if any path in freq_map extends beyond fixed_levels."""
    fixed_depth = len(category.fixed_levels)
    return any(len(p) > fixed_depth for p in freq_map)


def _all_levels_enumerated(category: Category) -> bool:
    return bool(category.fixed_levels) and all(
        lvl.mode == "enumerated" for lvl in category.fixed_levels
    )


def _enumerated_paths_fully_cover(category: Category, freq_map: dict[tuple[str, ...], int]) -> bool:
    """True when the observed paths are exactly the complete enumerated set.

    If the observed paths are a strict subset of all possible enumerated
    combinations, rename opportunities may still exist (e.g. only some parent
    values are represented). We only skip when the observed paths match the
    *complete* set of enumerated combinations — meaning there is nothing to
    rename.
    """
    levels = category.fixed_levels
    if not levels:
        return False

    def _level_values(lvl: FixedLevel, parent_val: str | None) -> list[str]:
        if lvl.values is not None:
            return [v.id for v in lvl.values]
        if lvl.values_by_parent is not None and parent_val is not None:
            return [v.id for v in lvl.values_by_parent.get(parent_val, [])]
        return []

    # Build all valid enumerated path tuples via layer-by-layer expansion
    current_prefixes: list[tuple[str, ...]] = [()]
    for lvl in levels:
        next_prefixes: list[tuple[str, ...]] = []
        for prefix in current_prefixes:
            parent_val = prefix[-1] if prefix else None
            for val_id in _level_values(lvl, parent_val):
                next_prefixes.append((*prefix, val_id))
        current_prefixes = next_prefixes
    all_enum_paths = set(current_prefixes)

    observed = set(freq_map.keys())
    return observed == all_enum_paths


def _build_user_prompt(category: Category, freq_map: dict[tuple[str, ...], int]) -> str:
    lines = [f"カテゴリ: {category.id}", ""]
    if category.fixed_levels:
        lines.append("固定層:")
        for i, lvl in enumerate(category.fixed_levels):
            lines.append(f"  {i}: {lvl.name} ({lvl.mode})")
        lines.append("")
    lines.append("現在の path 一覧 (snippet 数):")
    for path_tuple, count in sorted(freq_map.items()):
        lines.append(f"- {list(path_tuple)} : {count}")
    return "\n".join(lines)


def _validate_rename(
    rename: dict[str, Any],
    cat_by_id: dict[str, Category],
    available: dict[str, dict[tuple[str, ...], int]],
) -> None:
    cat_id = rename.get("category")
    src = rename.get("from_path")
    dst = rename.get("to_path")
    if not isinstance(cat_id, str) or not isinstance(src, list) or not isinstance(dst, list):
        raise ValueError(f"consolidate: malformed rename entry: {rename!r}")
    if cat_id not in cat_by_id:
        raise ValueError(f"consolidate: unknown category in rename: {cat_id!r}")
    if cat_id not in available or tuple(src) not in available[cat_id]:
        raise ValueError(f"consolidate: unknown source path in rename: {cat_id}/{src}")

    cat = cat_by_id[cat_id]
    for i, lvl in enumerate(cat.fixed_levels):
        if lvl.mode != "enumerated":
            continue
        src_v = src[i] if i < len(src) else None
        dst_v = dst[i] if i < len(dst) else None
        if src_v != dst_v:
            raise ValueError(
                f"consolidate: rename cannot change enumerated layer "
                f"'{lvl.name}': {src_v!r} -> {dst_v!r}"
            )


def _rewrite_classified_path(
    classified_dir: Path, category: str, src: list[str], dst: list[str]
) -> None:
    cat_dir = classified_dir / category
    for path in sorted(cat_dir.glob("*.md")):
        fm, body = read_frontmatter(path, ClassifiedFrontmatter)
        if fm is None or list(fm.path) != list(src):
            continue
        new_fm = ClassifiedFrontmatter(**{**fm.model_dump(), "path": list(dst)})
        write_frontmatter(path, new_fm, body)


def _tombstone_wiki_page(
    wiki_dir: Path,
    category: str,
    src: list[str],
    dst: list[str],
    reason: str,
    now: datetime,
) -> None:
    old_wiki = wiki_dir / category / Path(*src).with_suffix(".md")
    if not old_wiki.exists():
        return
    src_label = "/".join(src)
    dst_label = "/".join(dst)
    tombstone_fm = WikiFrontmatter(
        title=f"統合済み: {src_label}",
        category=category,
        path=src,
        sources=[],
        updated_at=now,
        tombstone=True,
        merged_into_path=dst,
        merged_at=now,
    )
    dst_rel = Path(*dst).with_suffix(".md").as_posix()
    body_lines = [
        f"# 統合済み: {src_label}",
        "",
        f"このページは [{dst_label}](../{dst_rel}) に統合されました。",
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
        f"{len(renames)} 件の path を統合した。",
        "",
    ]
    for r in renames:
        cat = r["category"]
        src_label = "/".join(r["from_path"])
        dst_label = "/".join(r["to_path"])
        lines.append(f"- `{cat}/{src_label}` → `{cat}/{dst_label}`")
        reason = r.get("reason")
        if reason:
            lines.append(f"  - 理由: {reason}")
    lines.append("")
    lines.append("---")
    lines.append("")
    new_block = "\n".join(lines)
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(existing + new_block, encoding="utf-8")


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    classified_dir: Path,
    wiki_dir: Path,
    log_path: Path,
    manifest_path: Path,
    system_prompt: str,
    now: Callable[[], datetime] = _now_utc,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    debug_dir = root / "state" / "debug"

    manifest = Manifest.load(manifest_path)
    cat_by_id = {c.id: c for c in categories}

    by_cat = _collect_path_frequencies(classified_dir)
    if not by_cat:
        return

    all_renames: list[dict[str, Any]] = []
    for cat_id, freq_map in by_cat.items():
        cat = cat_by_id.get(cat_id)
        if cat is None:
            continue

        if (
            _all_levels_enumerated(cat)
            and not _has_free_tail(cat, freq_map)
            and _enumerated_paths_fully_cover(cat, freq_map)
        ):
            continue

        new_hash = _hash_frequency_map(freq_map)
        prior = manifest.consolidate.get(cat_id, {}).get("path_frequency_hash")
        if prior == new_hash:
            continue

        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(cat, freq_map),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="consolidate", debug_dir=debug_dir)
        renames = parsed.get("renames", [])
        for r in renames:
            _validate_rename(r, cat_by_id, by_cat)
        all_renames.extend(renames)

        manifest.consolidate[cat_id] = {
            "path_frequency_hash": new_hash,
            "last_run_at": now().isoformat(),
        }

    if all_renames:
        ts = now()
        for r in all_renames:
            cat_id = r["category"]
            src = list(r["from_path"])
            dst = list(r["to_path"])
            reason = r.get("reason", "")
            _rewrite_classified_path(classified_dir, cat_id, src, dst)
            _tombstone_wiki_page(wiki_dir, cat_id, src, dst, reason, ts)
        _append_log(log_path, all_renames, ts)

    refreshed = _collect_path_frequencies(classified_dir)
    manifest.known_paths_cache = {
        cat_id: sorted(list(p) for p in fm.keys()) for cat_id, fm in refreshed.items()
    }
    manifest.save(manifest_path)
