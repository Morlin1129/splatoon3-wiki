from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Manifest:
    raw: dict[str, dict[str, Any]] = field(default_factory=dict)
    snippets: dict[str, dict[str, Any]] = field(default_factory=dict)
    wiki: dict[str, dict[str, Any]] = field(default_factory=dict)
    consolidate: dict[str, dict[str, Any]] = field(default_factory=dict)
    known_paths_cache: dict[str, list[list[str]]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            raw=data.get("raw", {}),
            snippets=data.get("snippets", {}),
            wiki=data.get("wiki", {}),
            consolidate=data.get("consolidate", {}),
            known_paths_cache=data.get("known_paths_cache", {}),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "raw": self.raw,
                    "snippets": self.snippets,
                    "wiki": self.wiki,
                    "consolidate": self.consolidate,
                    "known_paths_cache": self.known_paths_cache,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
