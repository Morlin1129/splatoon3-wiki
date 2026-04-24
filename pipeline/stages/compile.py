from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import Category, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.state import Manifest


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _fingerprint(paths: list[str]) -> str:
    joined = "\n".join(sorted(paths))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _load_snippets(root: Path, paths: list[str]) -> tuple[list[str], set[str]]:
    bodies: list[str] = []
    source_files: set[str] = set()
    for rel in paths:
        fm, body = read_frontmatter(root / rel, ClassifiedFrontmatter)
        assert fm is not None
        bodies.append(body.strip())
        source_files.add(fm.source_file)
    return bodies, source_files


def _build_user_prompt(category_label: str, subtopic: str, bodies: list[str]) -> str:
    numbered = "\n\n".join(f"{i + 1}. {b}" for i, b in enumerate(bodies))
    return f"Category: {category_label}\nSubtopic: {subtopic}\n\nSnippets:\n{numbered}"


def _with_sources(body: str, sources: list[str]) -> str:
    if not sources:
        return body.rstrip() + "\n"
    lines = ["", "## 出典", ""]
    for url in sources:
        lines.append(f"- {url}")
    lines.append("")
    return body.rstrip() + "\n\n" + "\n".join(lines)


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    classified_dir: Path,
    wiki_dir: Path,
    clusters_path: Path,
    manifest_path: Path,
    prompt_path: Path,
    source_urls: dict[str, str],
    now: Callable[[], datetime] = _now_utc,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))
    manifest = Manifest.load(manifest_path)
    system_prompt = prompt_path.read_text(encoding="utf-8")
    label_by_id = {c.id: c.label for c in categories}

    for key, paths in clusters.items():
        category_id, subtopic = key.split("/", 1)
        wiki_rel = f"wiki/{category_id}/{subtopic}.md"
        fingerprint = _fingerprint(paths)

        prior = manifest.wiki.get(wiki_rel, {}).get("cluster_fingerprint")
        if prior == fingerprint:
            continue

        bodies, source_files = _load_snippets(root, paths)
        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(label_by_id[category_id], subtopic, bodies),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
        )

        sources = sorted(source_urls[s] for s in source_files if s in source_urls)
        final_body = _with_sources(reply, sources)
        updated_at = now()

        fm = WikiFrontmatter(
            category=category_id,
            subtopic=subtopic,
            sources=sources,
            updated_at=updated_at,
        )
        out = wiki_dir / category_id / f"{subtopic}.md"
        write_frontmatter(out, fm, final_body)

        manifest.wiki[wiki_rel] = {"cluster_fingerprint": fingerprint}

    manifest.save(manifest_path)
