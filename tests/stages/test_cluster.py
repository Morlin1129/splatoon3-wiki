import json
from datetime import datetime
from pathlib import Path

from pipeline.frontmatter_io import write_frontmatter
from pipeline.models import ClassifiedFrontmatter
from pipeline.stages import cluster


def _seed(workspace: Path, category: str, name: str, path: list[str]) -> Path:
    file_path = workspace / "classified" / category / name
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 1),
        content_hash="h1",
        category=category,
        path=path,
    )
    write_frontmatter(file_path, fm, "本文")
    return file_path


def test_cluster_groups_by_full_path(tmp_path: Path) -> None:
    _seed(tmp_path, "03-weapon-role", "a.md", ["シューター", "スプラシューター", "ギア構成"])
    _seed(tmp_path, "03-weapon-role", "b.md", ["シューター", "スプラシューター", "ギア構成"])
    _seed(tmp_path, "03-weapon-role", "c.md", ["シューター", "スプラシューター", "立ち回り"])

    clusters_path = tmp_path / "state" / "clusters.json"
    cluster.run(
        classified_dir=tmp_path / "classified",
        clusters_path=clusters_path,
    )

    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    assert "03-weapon-role/シューター/スプラシューター/ギア構成" in data
    assert len(data["03-weapon-role/シューター/スプラシューター/ギア構成"]) == 2
    assert "03-weapon-role/シューター/スプラシューター/立ち回り" in data


def test_cluster_handles_single_layer_path(tmp_path: Path) -> None:
    _seed(tmp_path, "01-principles", "a.md", ["dakai-fundamentals"])
    clusters_path = tmp_path / "state" / "clusters.json"
    cluster.run(
        classified_dir=tmp_path / "classified",
        clusters_path=clusters_path,
    )
    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    assert "01-principles/dakai-fundamentals" in data


def test_cluster_writes_relative_paths_under_workspace(tmp_path: Path) -> None:
    """Each snippet entry stored in clusters.json is a workspace-relative path
    starting with 'classified/'."""
    _seed(tmp_path, "01-principles", "x.md", ["foo"])
    clusters_path = tmp_path / "state" / "clusters.json"
    cluster.run(
        classified_dir=tmp_path / "classified",
        clusters_path=clusters_path,
    )
    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    assert data["01-principles/foo"] == ["classified/01-principles/x.md"]
