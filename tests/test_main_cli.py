import json
import subprocess
from pathlib import Path

import pytest

from pipeline import main


def test_parse_args_single_stage() -> None:
    args = main.parse_args(["--stage", "ingest"])
    assert args.stage == "ingest"
    assert args.all is False


def test_parse_args_all() -> None:
    args = main.parse_args(["--all"])
    assert args.all is True


def test_parse_args_requires_one(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        main.parse_args([])


def test_parse_args_rejects_unknown_stage() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--stage", "bogus"])


def test_parse_args_accepts_index_stage() -> None:
    args = main.parse_args(["--stage", "index"])
    assert args.stage == "index"


def test_parse_args_accepts_consolidate_stage() -> None:
    args = main.parse_args(["--stage", "consolidate"])
    assert args.stage == "consolidate"


def test_stage_names_order_runs_consolidate_between_classify_and_cluster() -> None:
    names = main.STAGE_NAMES
    assert names.index("consolidate") == names.index("classify") + 1
    assert names.index("cluster") == names.index("consolidate") + 1


def _bare_workspace(tmp_path: Path, stages: list[str]) -> None:
    """Create a minimal workspace with empty input dirs and configs so main()
    can run without errors. The stages argument controls what's in pipeline.yaml."""
    for sub in ["sample_raw", "snippets", "classified", "wiki", "state"]:
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "categories.yaml").write_text("categories: []\n", encoding="utf-8")
    stages_yaml = "stages:\n"
    for stage in stages:
        stages_yaml += f"  {stage}: {{provider: fake, model: x, max_tokens: 1}}\n"
    (tmp_path / "config" / "pipeline.yaml").write_text(stages_yaml, encoding="utf-8")
    # Provide an empty prompts dir for stages that need build_system_prompt
    prompts_dir = tmp_path / "pipeline" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for stage in stages:
        (prompts_dir / f"{stage}.md").write_text("PROMPT", encoding="utf-8")


def test_rebuild_all_clears_full_manifest(tmp_path: Path) -> None:
    """--all --rebuild deletes the manifest entirely before running."""
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"raw": {}, "snippets": {"x.md": {"classified": true}}, "wiki": {}}\n',
        encoding="utf-8",
    )

    all_stages = ["ingest", "classify", "consolidate", "cluster", "compile", "index", "diff"]
    _bare_workspace(tmp_path, all_stages)
    # diff stage requires git repo; init one
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)

    main.main(["--all", "--rebuild", "--root", str(tmp_path)])

    # After --all --rebuild, manifest is recreated by stages running. The seeded
    # snippets entry "x.md" should be gone.
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "x.md" not in data.get("snippets", {})


def test_rebuild_classify_stage_clears_classified_flags(tmp_path: Path) -> None:
    """--stage classify --rebuild flips snippets[].classified to false but
    preserves other manifest data."""
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "raw": {"r.md": {"content_hash": "h"}},
                "snippets": {
                    "snippets/a.md": {
                        "source_hash": "h1",
                        "classified": True,
                        "classified_path": ["x"],
                    },
                    "snippets/b.md": {
                        "source_hash": "h2",
                        "classified": True,
                        "classified_path": ["y"],
                    },
                },
                "wiki": {"wiki/01-principles/x.md": {"cluster_fingerprint": "f"}},
                "consolidate": {"01-principles": {"path_frequency_hash": "h"}},
                "known_paths_cache": {"01-principles": [["x"], ["y"]]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _bare_workspace(tmp_path, ["classify"])

    main.main(["--stage", "classify", "--rebuild", "--root", str(tmp_path)])

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["snippets"]["snippets/a.md"]["classified"] is False
    assert "classified_path" not in data["snippets"]["snippets/a.md"]
    assert data["known_paths_cache"] == {}
    assert data["wiki"]["wiki/01-principles/x.md"]["cluster_fingerprint"] == "f"
    assert data["consolidate"]["01-principles"]["path_frequency_hash"] == "h"


def test_rebuild_consolidate_clears_consolidate_only(tmp_path: Path) -> None:
    """--stage consolidate --rebuild clears just manifest.consolidate."""
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "raw": {},
                "snippets": {"snippets/a.md": {"source_hash": "h", "classified": True}},
                "wiki": {},
                "consolidate": {"01-principles": {"path_frequency_hash": "h"}},
                "known_paths_cache": {"01-principles": [["x"]]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _bare_workspace(tmp_path, ["consolidate"])

    main.main(["--stage", "consolidate", "--rebuild", "--root", str(tmp_path)])

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["consolidate"] == {}
    assert data["snippets"]["snippets/a.md"]["classified"] is True


def test_rebuild_compile_clears_wiki_fingerprints(tmp_path: Path) -> None:
    """--stage compile --rebuild clears wiki entries."""
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "raw": {},
                "snippets": {},
                "wiki": {"wiki/01-principles/x.md": {"cluster_fingerprint": "f"}},
                "consolidate": {},
                "known_paths_cache": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _bare_workspace(tmp_path, ["compile"])
    (tmp_path / "state" / "clusters.json").write_text("{}", encoding="utf-8")

    main.main(["--stage", "compile", "--rebuild", "--root", str(tmp_path)])

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["wiki"] == {}
