import json
import subprocess
from datetime import datetime
from pathlib import Path

from pipeline.config import Category, FixedLevel, LevelValue, StageConfig
from pipeline.llm.fake import FakeLLMProvider
from pipeline.stages import classify, cluster, consolidate, diff_commit, index, ingest
from pipeline.stages import compile as compile_stage


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True)


def test_pipeline_end_to_end_single_layer_path(tmp_path: Path) -> None:
    """E2E with a category that has no fixed_levels (path = [<llm-named>])."""
    root = tmp_path
    for sub in ["sample_raw", "snippets", "classified", "wiki", "state"]:
        (root / sub).mkdir(parents=True, exist_ok=True)

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
                [{"slug": "amabi-right-high", "content": "右高台の制圧はリスクあり。"}],
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
        system_prompt="INGEST",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )

    classify_provider = FakeLLMProvider(
        responses=[json.dumps({"category": "02-rule-stage", "path": ["海女美術-ガチエリア"]})]
    )
    classify.run(
        provider=classify_provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=categories,
        snippets_dir=root / "snippets",
        classified_dir=root / "classified",
        manifest_path=root / "state" / "ingest_manifest.json",
        system_prompt="CLASSIFY",
        root=root,
    )

    consolidate_provider = FakeLLMProvider(
        responses=[json.dumps({"renames": []}, ensure_ascii=False)]
    )
    consolidate.run(
        provider=consolidate_provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=categories,
        classified_dir=root / "classified",
        wiki_dir=root / "wiki",
        log_path=root / "state" / "consolidate_log.md",
        manifest_path=root / "state" / "ingest_manifest.json",
        system_prompt="CONSOLIDATE",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )
    assert len(consolidate_provider.calls) == 1
    assert not (root / "state" / "consolidate_log.md").exists()

    cluster.run(
        classified_dir=root / "classified",
        clusters_path=root / "state" / "clusters.json",
    )

    compile_provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "title": "海女美術 ガチエリアの右高台運用",
                    "body": "## 海女美術 ガチエリア\n\n本文。",
                },
                ensure_ascii=False,
            )
        ]
    )
    compile_stage.run(
        provider=compile_provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=8192),
        categories=categories,
        classified_dir=root / "classified",
        wiki_dir=root / "wiki",
        clusters_path=root / "state" / "clusters.json",
        manifest_path=root / "state" / "ingest_manifest.json",
        system_prompt="COMPILE",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )

    index.run(wiki_dir=root / "wiki", categories=categories)

    committed = diff_commit.run(repo_root=root, wiki_dir=root / "wiki")
    assert committed is True

    wiki_page = root / "wiki" / "02-rule-stage" / "海女美術-ガチエリア.md"
    assert wiki_page.exists()
    assert "本文。" in wiki_page.read_text(encoding="utf-8")
    assert (root / "wiki" / "README.md").exists()
    assert (root / "wiki" / "02-rule-stage" / "README.md").exists()


def test_pipeline_end_to_end_multi_level_path(tmp_path: Path) -> None:
    """E2E with a 3-layer path: 03-weapon-role/shooter/splash-shooter/ギア構成."""
    root = tmp_path
    for sub in ["sample_raw", "snippets", "classified", "wiki", "state"]:
        (root / sub).mkdir(parents=True, exist_ok=True)

    (root / "sample_raw" / "2026-04-01-shooter.md").write_text(
        "スプラシューターのギア構成について。", encoding="utf-8"
    )
    _init_repo(root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)

    categories = [
        Category(
            id="03-weapon-role",
            label="ブキ・役割",
            description="ノウハウ",
            fixed_levels=[
                FixedLevel(
                    name="ブキ種別",
                    mode="enumerated",
                    values=[LevelValue(id="shooter", label="シューター")],
                ),
                FixedLevel(
                    name="個別ブキ",
                    mode="enumerated",
                    values_by_parent={
                        "shooter": [LevelValue(id="splash-shooter", label="スプラシューター")]
                    },
                ),
            ],
        )
    ]

    ingest.run(
        provider=FakeLLMProvider(
            responses=[
                json.dumps(
                    [{"slug": "splash-gear", "content": "スプラシューターのギア構成。"}],
                    ensure_ascii=False,
                )
            ]
        ),
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=4096),
        raw_dir=root / "sample_raw",
        snippets_dir=root / "snippets",
        manifest_path=root / "state" / "ingest_manifest.json",
        system_prompt="INGEST",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )

    classify.run(
        provider=FakeLLMProvider(
            responses=[
                json.dumps(
                    {
                        "category": "03-weapon-role",
                        "path": ["shooter", "splash-shooter", "ギア構成"],
                    }
                )
            ]
        ),
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=categories,
        snippets_dir=root / "snippets",
        classified_dir=root / "classified",
        manifest_path=root / "state" / "ingest_manifest.json",
        system_prompt="CLASSIFY",
        root=root,
    )

    # Free tail "ギア構成" exists below 2 enumerated layers, so consolidate IS called
    # (only enumerated-only with no free tail is skipped).
    consolidate.run(
        provider=FakeLLMProvider(responses=[json.dumps({"renames": []}, ensure_ascii=False)]),
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=categories,
        classified_dir=root / "classified",
        wiki_dir=root / "wiki",
        log_path=root / "state" / "consolidate_log.md",
        manifest_path=root / "state" / "ingest_manifest.json",
        system_prompt="CONSOLIDATE",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )

    cluster.run(
        classified_dir=root / "classified",
        clusters_path=root / "state" / "clusters.json",
    )

    compile_stage.run(
        provider=FakeLLMProvider(
            responses=[
                json.dumps(
                    {"title": "スプラシューターのギア構成", "body": "## ギア\n\n本文。"},
                    ensure_ascii=False,
                )
            ]
        ),
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=8192),
        categories=categories,
        classified_dir=root / "classified",
        wiki_dir=root / "wiki",
        clusters_path=root / "state" / "clusters.json",
        manifest_path=root / "state" / "ingest_manifest.json",
        system_prompt="COMPILE",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )

    index.run(wiki_dir=root / "wiki", categories=categories)

    leaf = root / "wiki" / "03-weapon-role" / "shooter" / "splash-shooter" / "ギア構成.md"
    assert leaf.exists()
    assert (root / "wiki" / "03-weapon-role" / "README.md").exists()
    assert (root / "wiki" / "03-weapon-role" / "shooter" / "README.md").exists()
    assert (root / "wiki" / "03-weapon-role" / "shooter" / "splash-shooter" / "README.md").exists()
    splash_readme = (
        root / "wiki" / "03-weapon-role" / "shooter" / "splash-shooter" / "README.md"
    ).read_text(encoding="utf-8")
    assert "ギア構成" in splash_readme
