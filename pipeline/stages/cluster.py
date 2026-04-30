from __future__ import annotations

import json
from pathlib import Path

from pipeline.frontmatter_io import read_frontmatter
from pipeline.models import ClassifiedFrontmatter


def run(*, classified_dir: Path, clusters_path: Path) -> None:
    clusters: dict[str, list[str]] = {}

    for path in sorted(classified_dir.rglob("*.md")):
        fm, _ = read_frontmatter(path, ClassifiedFrontmatter)
        if fm is None:
            raise RuntimeError(f"unreachable: classified missing frontmatter: {path}")
        key = f"{fm.category}/{'/'.join(fm.path)}"
        rel = str(path.relative_to(classified_dir.parent))
        clusters.setdefault(key, []).append(rel)

    for key in clusters:
        clusters[key].sort()

    clusters_path.parent.mkdir(parents=True, exist_ok=True)
    clusters_path.write_text(
        json.dumps(clusters, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
