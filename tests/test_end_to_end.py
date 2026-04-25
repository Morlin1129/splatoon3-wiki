import json
import subprocess
from datetime import datetime
from pathlib import Path

from pipeline.config import Category, StageConfig
from pipeline.llm.fake import FakeLLMProvider
from pipeline.stages import classify, cluster, diff_commit, ingest
from pipeline.stages import compile as compile_stage


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True)


def test_pipeline_end_to_end_with_fake_llm(tmp_path: Path) -> None:
    root = tmp_path
    for sub in [
        "sample_raw",
        "snippets",
        "classified",
        "wiki",
        "state",
        "pipeline/prompts",
    ]:
        (root / sub).mkdir(parents=True, exist_ok=True)

    (root / "pipeline" / "prompts" / "ingest.md").write_text("INGEST", encoding="utf-8")
    (root / "pipeline" / "prompts" / "classify.md").write_text("CLASSIFY", encoding="utf-8")
    (root / "pipeline" / "prompts" / "compile.md").write_text("COMPILE", encoding="utf-8")

    (root / "sample_raw" / "2026-04-01-notes.md").write_text("右高台の話など。", encoding="utf-8")
    _init_repo(root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)

    categories = [
        Category(id="02-rule-stage", label="ルール×ステージ", description="定石"),
    ]

    ingest_provider = FakeLLMProvider(
        responses=[
            json.dumps(
                [
                    {
                        "slug": "amabi-right-high",
                        "content": "右高台の制圧はリスクあり。",
                    }
                ],
                ensure_ascii=False,
            )
        ]
    )
    ingest.run(
        provider=ingest_provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=4096),
        raw_dir=root / "sample_raw",
        snippets_dir=root / "snippets",
        manifest_path=root / "state" / "ingest_manifest.json",
        prompt_path=root / "pipeline" / "prompts" / "ingest.md",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )

    classify_provider = FakeLLMProvider(
        responses=[json.dumps({"category": "02-rule-stage", "subtopic": "海女美術-ガチエリア"})]
    )
    classify.run(
        provider=classify_provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=categories,
        snippets_dir=root / "snippets",
        classified_dir=root / "classified",
        manifest_path=root / "state" / "ingest_manifest.json",
        prompt_path=root / "pipeline" / "prompts" / "classify.md",
        root=root,
    )

    cluster.run(
        classified_dir=root / "classified",
        clusters_path=root / "state" / "clusters.json",
    )

    compile_provider = FakeLLMProvider(responses=["## 海女美術 ガチエリア\n\n本文。"])
    compile_stage.run(
        provider=compile_provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=8192),
        categories=categories,
        classified_dir=root / "classified",
        wiki_dir=root / "wiki",
        clusters_path=root / "state" / "clusters.json",
        manifest_path=root / "state" / "ingest_manifest.json",
        prompt_path=root / "pipeline" / "prompts" / "compile.md",
        source_urls={},
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )

    committed = diff_commit.run(repo_root=root, wiki_dir=root / "wiki")
    assert committed is True

    wiki_page = root / "wiki" / "02-rule-stage" / "海女美術-ガチエリア.md"
    assert wiki_page.exists()
    assert "本文。" in wiki_page.read_text(encoding="utf-8")
