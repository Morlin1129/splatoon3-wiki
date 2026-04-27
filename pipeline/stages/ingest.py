from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import StageConfig
from pipeline.frontmatter_io import write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import SnippetFrontmatter
from pipeline.slug import slugify
from pipeline.state import Manifest

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _source_date(path: Path) -> str:
    m = _DATE_PREFIX.match(path.name)
    if m:
        return m.group(1)
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_llm_response(text: str, *, debug_dir: Path | None) -> list[dict]:
    data = parse_json_response(text, stage="ingest", debug_dir=debug_dir)
    if not isinstance(data, list):
        raise ValueError("ingest LLM response must be a JSON array")
    return data


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    raw_dir: Path,
    snippets_dir: Path,
    manifest_path: Path,
    system_prompt: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    root: Path | None = None,
) -> None:
    root = root or raw_dir.parent
    manifest = Manifest.load(manifest_path)
    debug_dir = root / "state" / "debug"

    for raw_file in sorted(raw_dir.glob("*.md")):
        rel = str(raw_file.relative_to(root))
        file_hash = _hash_file(raw_file)

        prior = manifest.raw.get(rel)
        if prior and prior.get("content_hash") == file_hash:
            continue  # no change, skip LLM call

        body = raw_file.read_text(encoding="utf-8")
        reply = provider.complete(
            system=system_prompt,
            user=body,
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        items = _parse_llm_response(reply, debug_dir=debug_dir)
        src_date = _source_date(raw_file)
        extracted_at = now()

        for item in items:
            slug = slugify(item["slug"])
            out_path = snippets_dir / f"{src_date}-{slug}.md"
            fm = SnippetFrontmatter(
                source_file=rel,
                source_date=src_date,
                extracted_at=extracted_at,
                content_hash=file_hash,
            )
            write_frontmatter(out_path, fm, item["content"])
            manifest.snippets[str(out_path.relative_to(root))] = {
                "source_hash": file_hash,
                "classified": False,
            }

        manifest.raw[rel] = {
            "content_hash": file_hash,
            "ingested_at": extracted_at.isoformat(),
        }

    manifest.save(manifest_path)
