from __future__ import annotations

import json
from pathlib import Path

import yaml

from pipeline.config import Category, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.models import ClassifiedFrontmatter, SnippetFrontmatter
from pipeline.state import Manifest


def _build_user_prompt(
    categories: list[Category], snippet_body: str, known_subtopics: list[str]
) -> str:
    cat_yaml = yaml.safe_dump(
        {"categories": [c.model_dump() for c in categories]},
        allow_unicode=True,
        sort_keys=False,
    )
    known = "\n".join(f"- {s}" for s in sorted(set(known_subtopics))) or "(none yet)"
    return (
        f"{cat_yaml}\n\n"
        f"Existing subtopics (reuse when appropriate):\n{known}\n\n"
        f"Snippet body:\n---\n{snippet_body}\n---"
    )


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    snippets_dir: Path,
    classified_dir: Path,
    manifest_path: Path,
    prompt_path: Path,
    root: Path,
) -> None:
    manifest = Manifest.load(manifest_path)
    system_prompt = prompt_path.read_text(encoding="utf-8")
    valid_ids = {c.id for c in categories}

    known_subtopics = [
        p.stem for cat_dir in classified_dir.glob("*/") for p in cat_dir.glob("*.md")
    ]

    for snippet_path in sorted(snippets_dir.glob("*.md")):
        rel = str(snippet_path.relative_to(root))
        entry = manifest.snippets.get(rel)
        if entry and entry.get("classified"):
            continue

        fm, body = read_frontmatter(snippet_path, SnippetFrontmatter)
        if fm is None:
            raise RuntimeError(f"unreachable: snippet missing frontmatter: {snippet_path}")

        user = _build_user_prompt(categories, body, known_subtopics)
        reply = provider.complete(
            system=system_prompt,
            user=user,
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = json.loads(reply)
        category_id = parsed["category"]
        subtopic = parsed["subtopic"]
        if category_id not in valid_ids:
            raise ValueError(f"classify returned unknown category {category_id}")

        classified_fm = ClassifiedFrontmatter(
            **fm.model_dump(),
            category=category_id,
            subtopic=subtopic,
        )
        out = classified_dir / category_id / snippet_path.name
        write_frontmatter(out, classified_fm, body)
        known_subtopics.append(subtopic)

        if rel in manifest.snippets:
            manifest.snippets[rel]["classified"] = True
        else:
            manifest.snippets[rel] = {"source_hash": fm.content_hash, "classified": True}

    manifest.save(manifest_path)
