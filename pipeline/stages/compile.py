from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import Category, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
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
        if fm is None:
            raise RuntimeError(f"unreachable: classified missing frontmatter: {rel}")
        bodies.append(body.strip())
        source_files.add(fm.source_file)
    return bodies, source_files


def _build_user_prompt(category_label: str, path: list[str], bodies: list[str]) -> str:
    numbered = "\n\n".join(f"{i + 1}. {b}" for i, b in enumerate(bodies))
    path_str = " > ".join(path)
    return f"カテゴリー: {category_label}\nパス: {path_str}\n\nスニペット:\n{numbered}"


def _with_sources(body: str, sources: list[str]) -> str:
    if not sources:
        return body.rstrip() + "\n"
    lines = ["", "## 出典", ""]
    for url in sources:
        lines.append(f"- {url}")
    lines.append("")
    return body.rstrip() + "\n\n" + "\n".join(lines)


def _wiki_output_path(wiki_dir: Path, category_id: str, path: list[str]) -> Path:
    return wiki_dir / category_id / Path(*path).with_suffix(".md")


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    classified_dir: Path,
    wiki_dir: Path,
    clusters_path: Path,
    manifest_path: Path,
    system_prompt: str,
    source_urls: dict[str, str],
    now: Callable[[], datetime] = _now_utc,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))
    manifest = Manifest.load(manifest_path)
    label_by_id = {c.id: c.label for c in categories}
    debug_dir = root / "state" / "debug"

    for key, paths in clusters.items():
        category_id, *path_components = key.split("/")
        if not path_components:
            raise ValueError(f"compile: cluster key has no path: {key!r}")
        out_path = _wiki_output_path(wiki_dir, category_id, path_components)
        wiki_rel = str(out_path.relative_to(root))
        fingerprint = _fingerprint(paths)

        prior = manifest.wiki.get(wiki_rel, {}).get("cluster_fingerprint")
        if prior == fingerprint:
            continue

        bodies, source_files = _load_snippets(root, paths)
        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(label_by_id[category_id], path_components, bodies),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="compile", debug_dir=debug_dir)
        title = parsed["title"]
        body = parsed["body"]

        sources = sorted(source_urls[s] for s in source_files if s in source_urls)
        final_body = _with_sources(body, sources)
        updated_at = now()

        fm = WikiFrontmatter(
            title=title,
            category=category_id,
            path=path_components,
            sources=sources,
            updated_at=updated_at,
        )
        write_frontmatter(out_path, fm, final_body)

        manifest.wiki[wiki_rel] = {"cluster_fingerprint": fingerprint}

    manifest.save(manifest_path)
