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
