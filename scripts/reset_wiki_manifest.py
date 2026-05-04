"""Clear the `wiki` section of ingest_manifest.json so the compile stage
re-emits every wiki page on the next run.

Use after changing compile output format (e.g. adding new frontmatter fields
or new body sections) when you want existing pages refreshed even though
their cluster fingerprints have not changed.

Usage:
    uv run python scripts/reset_wiki_manifest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when running from anywhere.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.state import Manifest  # noqa: E402

MANIFEST_PATH = ROOT / "state" / "ingest_manifest.json"


def main() -> None:
    manifest = Manifest.load(MANIFEST_PATH)
    cleared = len(manifest.wiki)
    manifest.wiki = {}
    manifest.save(MANIFEST_PATH)
    print(f"cleared {cleared} wiki manifest entries at {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
