from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.config import build_system_prompt, load_categories, load_pipeline
from pipeline.llm.base import get_provider
from pipeline.stages import classify, cluster, consolidate, diff_commit, index, ingest
from pipeline.stages import compile as compile_stage
from pipeline.state import Manifest

STAGE_NAMES = ["ingest", "classify", "consolidate", "cluster", "compile", "index", "diff"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pipeline", description="LLM Wiki generation pipeline")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage", choices=STAGE_NAMES, help="Run a single stage")
    group.add_argument("--all", action="store_true", help="Run all stages in order")
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Clear manifest fields relevant to the stage(s) before running",
    )
    p.add_argument("--root", type=Path, default=Path.cwd())
    return p.parse_args(argv)


def _apply_rebuild(stages_to_run: list[str], manifest_path: Path) -> None:
    """Clear manifest fields that the upcoming stage(s) would otherwise treat
    as cached results.

    --all --rebuild: delete the manifest entirely.
    --stage X --rebuild: clear only fields X depends on.
    """
    if not manifest_path.exists():
        return

    if set(stages_to_run) == set(STAGE_NAMES):
        manifest_path.unlink()
        return

    manifest = Manifest.load(manifest_path)
    for stage in stages_to_run:
        if stage == "ingest":
            manifest.raw = {}
        elif stage == "classify":
            for entry in manifest.snippets.values():
                entry["classified"] = False
                entry.pop("classified_path", None)
            manifest.known_paths_cache = {}
        elif stage == "consolidate":
            manifest.consolidate = {}
        elif stage == "compile":
            manifest.wiki = {}
        # cluster, index, diff: nothing to clear
    manifest.save(manifest_path)


def _run_stage(name: str, root: Path) -> None:
    pipeline_cfg = load_pipeline(root / "config" / "pipeline.yaml")
    categories = load_categories(root / "config" / "categories.yaml")
    manifest_path = root / "state" / "ingest_manifest.json"

    if name == "ingest":
        stage_cfg = pipeline_cfg.stages["ingest"]
        ingest.run(
            provider=get_provider(stage_cfg),
            stage_cfg=stage_cfg,
            raw_dir=root / "sample_raw",
            snippets_dir=root / "snippets",
            manifest_path=manifest_path,
            system_prompt=build_system_prompt(root, "ingest"),
            root=root,
        )
    elif name == "classify":
        stage_cfg = pipeline_cfg.stages["classify"]
        classify.run(
            provider=get_provider(stage_cfg),
            stage_cfg=stage_cfg,
            categories=categories,
            snippets_dir=root / "snippets",
            classified_dir=root / "classified",
            manifest_path=manifest_path,
            system_prompt=build_system_prompt(root, "classify"),
            root=root,
        )
    elif name == "consolidate":
        stage_cfg = pipeline_cfg.stages["consolidate"]
        consolidate.run(
            provider=get_provider(stage_cfg),
            stage_cfg=stage_cfg,
            categories=categories,
            classified_dir=root / "classified",
            wiki_dir=root / "wiki",
            log_path=root / "state" / "consolidate_log.md",
            manifest_path=manifest_path,
            system_prompt=build_system_prompt(root, "consolidate"),
            root=root,
        )
    elif name == "cluster":
        cluster.run(
            classified_dir=root / "classified",
            clusters_path=root / "state" / "clusters.json",
        )
    elif name == "compile":
        stage_cfg = pipeline_cfg.stages["compile"]
        compile_stage.run(
            provider=get_provider(stage_cfg),
            stage_cfg=stage_cfg,
            categories=categories,
            classified_dir=root / "classified",
            wiki_dir=root / "wiki",
            clusters_path=root / "state" / "clusters.json",
            manifest_path=manifest_path,
            system_prompt=build_system_prompt(root, "compile"),
            source_urls={},
            root=root,
        )
    elif name == "index":
        index.run(
            wiki_dir=root / "wiki",
            categories=categories,
        )
    elif name == "diff":
        diff_commit.run(repo_root=root, wiki_dir=root / "wiki")
    else:
        raise ValueError(f"unknown stage: {name}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    root = args.root.resolve()
    stages = STAGE_NAMES if args.all else [args.stage]
    if args.rebuild:
        manifest_path = root / "state" / "ingest_manifest.json"
        _apply_rebuild(stages, manifest_path)
    for name in stages:
        print(f"[pipeline] running stage: {name}")
        _run_stage(name, root)


if __name__ == "__main__":
    main()
