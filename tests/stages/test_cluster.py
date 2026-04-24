from datetime import datetime
from pathlib import Path

from pipeline.frontmatter_io import write_frontmatter
from pipeline.models import ClassifiedFrontmatter
from pipeline.stages import cluster


def _seed(path: Path, category: str, subtopic: str) -> None:
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
        category=category,
        subtopic=subtopic,
    )
    write_frontmatter(path, fm, "body")


def test_cluster_groups_by_category_subtopic(tmp_path: Path) -> None:
    classified = tmp_path / "classified"
    (classified / "02-rule-stage").mkdir(parents=True)
    (classified / "01-principles").mkdir()

    _seed(classified / "02-rule-stage" / "a.md", "02-rule-stage", "海女美術-ガチエリア")
    _seed(classified / "02-rule-stage" / "b.md", "02-rule-stage", "海女美術-ガチエリア")
    _seed(classified / "02-rule-stage" / "c.md", "02-rule-stage", "マテガイ-ガチホコ")
    _seed(classified / "01-principles" / "d.md", "01-principles", "人数有利")

    clusters_path = tmp_path / "state" / "clusters.json"

    cluster.run(classified_dir=classified, clusters_path=clusters_path)

    import json

    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    assert sorted(data["02-rule-stage/海女美術-ガチエリア"]) == [
        "classified/02-rule-stage/a.md",
        "classified/02-rule-stage/b.md",
    ]
    assert data["02-rule-stage/マテガイ-ガチホコ"] == ["classified/02-rule-stage/c.md"]
    assert data["01-principles/人数有利"] == ["classified/01-principles/d.md"]
