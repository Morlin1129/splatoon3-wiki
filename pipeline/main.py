from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.config import load_categories, load_pipeline
from pipeline.llm.base import get_provider
from pipeline.stages import classify, cluster, diff_commit, ingest
from pipeline.stages import compile as compile_stage

STAGE_NAMES = ["ingest", "classify", "cluster", "compile", "diff"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pipeline", description="LLM Wiki generation pipeline")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage", choices=STAGE_NAMES, help="Run a single stage")
    group.add_argument("--all", action="store_true", help="Run all stages in order")
    p.add_argument("--root", type=Path, default=Path.cwd())
    return p.parse_args(argv)


def _run_stage(name: str, root: Path) -> None:
    pipeline_cfg = load_pipeline(root / "config" / "pipeline.yaml")
    categories = load_categories(root / "config" / "categories.yaml")

    if name == "ingest":
        stage_cfg = pipeline_cfg.stages["ingest"]
        ingest.run(
            provider=get_provider(stage_cfg),
            stage_cfg=stage_cfg,
            raw_dir=root / "sample_raw",
            snippets_dir=root / "snippets",
            manifest_path=root / "state" / "ingest_manifest.json",
            prompt_path=root / "pipeline" / "prompts" / "ingest.md",
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
            manifest_path=root / "state" / "ingest_manifest.json",
            prompt_path=root / "pipeline" / "prompts" / "classify.md",
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
            manifest_path=root / "state" / "ingest_manifest.json",
            prompt_path=root / "pipeline" / "prompts" / "compile.md",
            source_urls={},
            root=root,
        )
    elif name == "diff":
        diff_commit.run(repo_root=root, wiki_dir=root / "wiki")
    else:
        raise ValueError(f"unknown stage: {name}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    root = args.root.resolve()
    stages = STAGE_NAMES if args.all else [args.stage]
    for name in stages:
        print(f"[pipeline] running stage: {name}")
        _run_stage(name, root)


if __name__ == "__main__":
    main()
