"""Migrate legacy subtopic-based frontmatter to path-based schema.

Usage:
    uv run python -m scripts.migrate_to_path [<workspace_root>]

Default workspace_root is the current working directory. The script:
1. Rewrites classified/*/*.md frontmatter (subtopic -> path: [subtopic])
2. Rewrites wiki/*/*.md frontmatter (subtopic -> path, merged_into -> merged_into_path)
3. Rebuilds state/ingest_manifest.json's known_paths_cache and adds
   classified_path entries to manifest.snippets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import frontmatter


def _migrate_frontmatter_file(path: Path) -> dict | None:
    """Migrate one .md file in place. Returns the new metadata dict (or None
    if the file had no frontmatter)."""
    text = path.read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    if not post.metadata:
        return None
    md = dict(post.metadata)
    changed = False

    if "subtopic" in md and "path" not in md:
        md["path"] = [md.pop("subtopic")]
        changed = True
    elif "subtopic" in md:
        # Both present? Trust path, drop legacy.
        del md["subtopic"]
        changed = True

    if "merged_into" in md and "merged_into_path" not in md:
        merged = md.pop("merged_into")
        md["merged_into_path"] = [merged] if merged is not None else None
        changed = True

    if changed:
        new_post = frontmatter.Post(post.content, **md)
        path.write_text(frontmatter.dumps(new_post) + "\n", encoding="utf-8")

    return md


def migrate_workspace(root: Path) -> None:
    classified_dir = root / "classified"
    wiki_dir = root / "wiki"
    manifest_path = root / "state" / "ingest_manifest.json"

    # 1. Migrate classified files; collect path data per category for cache.
    paths_by_cat: dict[str, list[list[str]]] = defaultdict(list)
    if classified_dir.exists():
        for f in sorted(classified_dir.rglob("*.md")):
            md = _migrate_frontmatter_file(f)
            if md is None:
                continue
            cat = md.get("category")
            path = md.get("path")
            if isinstance(cat, str) and isinstance(path, list):
                paths_by_cat[cat].append(list(path))

    # 2. Migrate wiki files (frontmatter only; file locations unchanged for 1-layer).
    if wiki_dir.exists():
        for f in sorted(wiki_dir.rglob("*.md")):
            _migrate_frontmatter_file(f)

    # 3. Rebuild manifest's known_paths_cache, add classified_path to each snippet.
    if not manifest_path.exists():
        return
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # known_paths_cache: deduplicate
    cache: dict[str, list[list[str]]] = {}
    for cat, plist in paths_by_cat.items():
        seen: list[list[str]] = []
        for p in plist:
            if p not in seen:
                seen.append(p)
        cache[cat] = sorted(seen)
    data["known_paths_cache"] = cache

    # classified_path on snippets: read from corresponding classified file
    snippets = data.get("snippets", {})
    for snippet_rel, entry in snippets.items():
        if not entry.get("classified"):
            continue
        if "classified_path" in entry:
            continue
        snippet_name = Path(snippet_rel).name
        for f in classified_dir.rglob(snippet_name):
            post = frontmatter.loads(f.read_text(encoding="utf-8"))
            p = post.metadata.get("path")
            if isinstance(p, list):
                entry["classified_path"] = list(p)
            break

    data.setdefault("consolidate", {})

    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="migrate_to_path")
    p.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = p.parse_args(argv)
    migrate_workspace(args.root.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
