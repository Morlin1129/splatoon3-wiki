from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.config import Category, FixedLevel, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter, SnippetFrontmatter
from pipeline.state import Manifest


def _enumerated_ids_at(level: FixedLevel, parent_id: str | None) -> set[str]:
    if level.values is not None:
        return {v.id for v in level.values}
    if level.values_by_parent is not None and parent_id is not None:
        return {v.id for v in level.values_by_parent.get(parent_id, [])}
    return set()


def _validate_path(category: Category, path: list[str]) -> None:
    """Raise ValueError if path violates fixed_levels mode constraints."""
    if not path:
        raise ValueError(f"classify returned empty path for category {category.id}")
    parent_id: str | None = None
    for i, level in enumerate(category.fixed_levels):
        if i >= len(path):
            raise ValueError(
                f"path is shorter than fixed_levels for category {category.id}: "
                f"path={path}, expected >= {len(category.fixed_levels)} components"
            )
        component = path[i]
        if level.mode == "enumerated":
            allowed = _enumerated_ids_at(level, parent_id)
            if component not in allowed:
                raise ValueError(
                    f"category {category.id} level '{level.name}' (enumerated): "
                    f"value {component!r} not in allowed ids {sorted(allowed)}"
                )
            parent_id = component
        else:
            parent_id = None  # open level cannot drive child enumeration


def _build_user_prompt(
    categories: list[Category],
    snippet_body: str,
    known_paths: dict[str, list[list[str]]],
) -> str:
    cat_yaml = yaml.safe_dump(
        {"categories": [c.model_dump() for c in categories]},
        allow_unicode=True,
        sort_keys=False,
    )
    if known_paths:
        path_lines: list[str] = []
        for cat_id, paths in sorted(known_paths.items()):
            for p in sorted(paths):
                path_lines.append(f"- {cat_id}: {'/'.join(p)}")
        known_block = "\n".join(path_lines)
    else:
        known_block = "(まだなし)"
    return (
        f"{cat_yaml}\n\n"
        f"既存の path 一覧（カテゴリ別、適切な場合は再利用してください）:\n{known_block}\n\n"
        f"スニペット本文:\n---\n{snippet_body}\n---"
    )


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    snippets_dir: Path,
    classified_dir: Path,
    manifest_path: Path,
    system_prompt: str,
    root: Path,
) -> None:
    manifest = Manifest.load(manifest_path)
    valid_ids = {c.id for c in categories}
    cat_by_id = {c.id: c for c in categories}
    debug_dir = root / "state" / "debug"

    for snippet_path in sorted(snippets_dir.glob("*.md")):
        rel = str(snippet_path.relative_to(root))
        entry = manifest.snippets.get(rel)
        if entry and entry.get("classified"):
            continue

        fm, body = read_frontmatter(snippet_path, SnippetFrontmatter)
        if fm is None:
            raise RuntimeError(f"unreachable: snippet missing frontmatter: {snippet_path}")

        user = _build_user_prompt(categories, body, manifest.known_paths_cache)
        reply = provider.complete(
            system=system_prompt,
            user=user,
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="classify", debug_dir=debug_dir)
        category_id = parsed["category"]
        path = parsed["path"]

        if category_id not in valid_ids:
            raise ValueError(f"classify returned unknown category {category_id}")
        if not isinstance(path, list) or not path:
            raise ValueError(f"classify returned invalid path: {path!r}")
        _validate_path(cat_by_id[category_id], list(path))

        classified_fm = ClassifiedFrontmatter(
            **fm.model_dump(),
            category=category_id,
            path=path,
        )
        out = classified_dir / category_id / snippet_path.name
        write_frontmatter(out, classified_fm, body)

        entry = manifest.snippets.setdefault(
            rel, {"source_hash": fm.content_hash, "classified": False}
        )
        entry["classified"] = True
        entry["classified_path"] = list(path)

        cache_list = manifest.known_paths_cache.setdefault(category_id, [])
        if list(path) not in cache_list:
            cache_list.append(list(path))

    manifest.save(manifest_path)
