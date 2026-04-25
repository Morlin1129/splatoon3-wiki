"""Helpers for parsing LLM JSON responses with debug-friendly errors."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n(.*?)\n```\s*$",
    re.DOTALL,
)


def strip_markdown_fence(text: str) -> str:
    """Strip a surrounding ```json ... ``` (or ``` ... ```) fence if present.

    Some LLMs return JSON wrapped in a markdown code fence even when JSON-only
    output was requested. Returns the inner text when a fence is detected;
    otherwise returns the original text unchanged.
    """
    match = _FENCE_PATTERN.match(text)
    if match:
        return match.group(1)
    return text


def parse_json_response(
    raw: str,
    *,
    stage: str,
    debug_dir: Path | None = None,
) -> Any:
    """Parse an LLM response as JSON, with debug visibility on failure.

    - Saves the raw response to `<debug_dir>/<stage>.txt` (overwrites each call)
      so the most recent response is always inspectable on disk.
    - Strips a surrounding markdown code fence if present.
    - On `JSONDecodeError`, raises `ValueError` with the first 200 characters
      of the raw response embedded in the message.
    """
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{stage}.txt").write_text(raw, encoding="utf-8")

    cleaned = strip_markdown_fence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        snippet = raw[:200].replace("\n", "\\n")
        raise ValueError(
            f"{stage} stage returned non-JSON response "
            f"(see debug_dir/{stage}.txt): {exc.msg} "
            f"-- first 200 chars: {snippet!r}"
        ) from exc
