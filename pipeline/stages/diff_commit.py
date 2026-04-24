from __future__ import annotations

import subprocess
from pathlib import Path


def _has_changes(repo_root: Path, rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", rel_path],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def run(
    *,
    repo_root: Path,
    wiki_dir: Path,
    message: str = "wiki: regenerate pages",
) -> bool:
    rel = wiki_dir.relative_to(repo_root)
    if not _has_changes(repo_root, str(rel)):
        return False
    subprocess.run(["git", "add", "--", str(rel)], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True)
    return True
