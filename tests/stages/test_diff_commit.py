import subprocess
from pathlib import Path

import pytest

from pipeline.stages import diff_commit


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "initial.md").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_commits_changes_when_wiki_modified(git_repo: Path) -> None:
    (git_repo / "wiki" / "new.md").write_text("hello", encoding="utf-8")

    result = diff_commit.run(repo_root=git_repo, wiki_dir=git_repo / "wiki")

    assert result is True
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "wiki:" in log.stdout


def test_noop_when_no_changes(git_repo: Path) -> None:
    result = diff_commit.run(repo_root=git_repo, wiki_dir=git_repo / "wiki")
    assert result is False
