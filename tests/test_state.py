from pathlib import Path

from pipeline.state import Manifest


def test_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "ingest_manifest.json"
    m = Manifest.load(path)

    assert m.raw == {}
    assert m.snippets == {}
    assert m.wiki == {}

    m.raw["sample_raw/a.md"] = {"content_hash": "h1", "ingested_at": "2026-04-24T00:00:00"}
    m.snippets["snippets/s1.md"] = {"source_hash": "h1", "classified": False}
    m.save(path)

    reloaded = Manifest.load(path)
    assert reloaded.raw["sample_raw/a.md"]["content_hash"] == "h1"
    assert reloaded.snippets["snippets/s1.md"]["classified"] is False


def test_manifest_missing_file_returns_empty(tmp_path: Path) -> None:
    m = Manifest.load(tmp_path / "does_not_exist.json")
    assert m.raw == {}


def test_manifest_persists_consolidate_field(tmp_path: Path) -> None:
    p = tmp_path / "manifest.json"
    m = Manifest(
        consolidate={
            "03-weapon-role": {
                "path_frequency_hash": "abc123",
                "last_run_at": "2026-04-30T10:00:00+00:00",
            }
        }
    )
    m.save(p)
    reloaded = Manifest.load(p)
    assert reloaded.consolidate["03-weapon-role"]["path_frequency_hash"] == "abc123"


def test_manifest_persists_known_paths_cache(tmp_path: Path) -> None:
    p = tmp_path / "manifest.json"
    m = Manifest(
        known_paths_cache={
            "03-weapon-role": [
                ["シューター", "スプラシューター", "ギア構成"],
                ["ローラー", "スプラローラー"],
            ]
        }
    )
    m.save(p)
    reloaded = Manifest.load(p)
    assert reloaded.known_paths_cache["03-weapon-role"][0] == [
        "シューター",
        "スプラシューター",
        "ギア構成",
    ]


def test_manifest_load_handles_missing_new_fields(tmp_path: Path) -> None:
    """Backward compat: existing manifests without new fields must load."""
    p = tmp_path / "manifest.json"
    p.write_text('{"raw": {}, "snippets": {}, "wiki": {}}\n', encoding="utf-8")
    m = Manifest.load(p)
    assert m.consolidate == {}
    assert m.known_paths_cache == {}
