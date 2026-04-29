# 階層タクソノミー × 差分実行 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 既存の 2 階層タクソノミー（`category` × `subtopic`）を可変深度の `path` 階層に拡張し、各ステージ（特に consolidate）に差分実行を導入する。Splatoon の `02-rule-stage` と `03-weapon-role` を多層化して PoC 検証する。

**Architecture:** データモデル変更（`subtopic: str` → `path: list[str]`）、`categories.yaml` のスキーマ刷新（`fixed_levels` で各層を `enumerated` または `open` モードで定義）、consolidate ステージにカテゴリ単位スキップ（`path_frequency_hash` ベース）を追加、classify に `known_paths_cache` を導入、index ステージを再帰化（中間ノードに静的索引 README）、CLI に `--rebuild` フラグ追加。詳細は spec [2026-04-30-hierarchical-taxonomy-and-incremental-execution-design.md](../specs/2026-04-30-hierarchical-taxonomy-and-incremental-execution-design.md) 参照。

**Tech Stack:** Python 3.12+, pydantic v2, pytest, uv, frontmatter (python-frontmatter), pyyaml

---

## 注意：Phase 2 の broken middle について

Phase 2 はデータモデルの「ハードカットオーバー」を行う。**Task 4（モデル更新）から Task 14（E2E 更新）の間は、既存テストの一部が失敗する状態が続く**。Phase 2 全体を 1 つの feature branch（例: `feat/path-taxonomy`）で進め、Phase 2 完了時点で main にマージする運用を推奨する。

各 Phase 末で `uv run pytest` が緑になることをゴールにする。

---

## Phase 1: スキーマ基盤（後方互換、各タスク独立コミット可能）

### Task 1: Category モデルに fixed_levels を追加

**Files:**
- Modify: `pipeline/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

`tests/test_config.py` に以下を追記:

```python
from pathlib import Path

import pytest

from pipeline.config import (
    Category,
    FixedLevel,
    LevelValue,
    load_categories,
)


def test_category_with_no_fixed_levels(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: 01-principles
    label: 原理原則
    description: 普遍理論
    fixed_levels: []
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cats = load_categories(p)
    assert len(cats) == 1
    assert cats[0].fixed_levels == []


def test_category_with_enumerated_level(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: 02-rule-stage
    label: ルール×ステージ
    description: x
    fixed_levels:
      - name: ルール
        mode: enumerated
        values:
          - id: area
            label: ガチエリア
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cats = load_categories(p)
    assert len(cats[0].fixed_levels) == 1
    lvl = cats[0].fixed_levels[0]
    assert lvl.mode == "enumerated"
    assert lvl.name == "ルール"
    assert lvl.values is not None
    assert lvl.values[0].id == "area"
    assert lvl.values[0].label == "ガチエリア"


def test_category_with_open_level(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: 05-glossary
    label: 用語集
    description: x
    fixed_levels:
      - name: 用語カテゴリ
        mode: open
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cats = load_categories(p)
    lvl = cats[0].fixed_levels[0]
    assert lvl.mode == "open"
    assert lvl.values is None
    assert lvl.values_by_parent is None


def test_category_with_values_by_parent(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: 03-weapon-role
    label: ブキ・役割
    description: x
    fixed_levels:
      - name: ブキ種別
        mode: enumerated
        values:
          - id: shooter
            label: シューター
          - id: roller
            label: ローラー
      - name: 個別ブキ
        mode: enumerated
        values_by_parent:
          shooter:
            - id: splash-shooter
              label: スプラシューター
          roller:
            - id: splat-roller
              label: スプラローラー
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cats = load_categories(p)
    levels = cats[0].fixed_levels
    assert levels[1].values_by_parent is not None
    assert "shooter" in levels[1].values_by_parent
    assert levels[1].values_by_parent["shooter"][0].id == "splash-shooter"


def test_open_mode_with_values_is_invalid(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: x
    label: x
    description: x
    fixed_levels:
      - name: lv1
        mode: open
        values:
          - id: a
            label: a
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="open"):
        load_categories(p)


def test_enumerated_mode_without_values_is_invalid(tmp_path: Path) -> None:
    yaml_text = """
categories:
  - id: x
    label: x
    description: x
    fixed_levels:
      - name: lv1
        mode: enumerated
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="enumerated"):
        load_categories(p)


def test_values_by_parent_keys_must_match_parent_ids(tmp_path: Path) -> None:
    # parent (lv0) has [shooter, roller] but values_by_parent only has [shooter]
    yaml_text = """
categories:
  - id: x
    label: x
    description: x
    fixed_levels:
      - name: lv0
        mode: enumerated
        values:
          - id: shooter
            label: シューター
          - id: roller
            label: ローラー
      - name: lv1
        mode: enumerated
        values_by_parent:
          shooter:
            - id: a
              label: a
"""
    p = tmp_path / "categories.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="values_by_parent"):
        load_categories(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `FixedLevel`, `LevelValue` not defined; `fixed_levels` field missing.

- [ ] **Step 3: Implement the new schema in `pipeline/config.py`**

`pipeline/config.py` を以下に置換（既存の `Category`, `Provider`, `StageConfig`, `PipelineConfig`, `load_pipeline`, `build_system_prompt` は維持し、新型を追加）:

```python
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

Provider = Literal["anthropic", "gemini", "fake"]
LevelMode = Literal["enumerated", "open"]


class LevelValue(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class FixedLevel(BaseModel):
    name: str = Field(min_length=1)
    mode: LevelMode
    values: list[LevelValue] | None = None
    values_by_parent: dict[str, list[LevelValue]] | None = None

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> "FixedLevel":
        if self.mode == "open":
            if self.values is not None or self.values_by_parent is not None:
                raise ValueError(
                    f"open mode level '{self.name}' must not have values/values_by_parent"
                )
        elif self.mode == "enumerated":
            if self.values is None and self.values_by_parent is None:
                raise ValueError(
                    f"enumerated mode level '{self.name}' must have values or values_by_parent"
                )
            if self.values is not None and self.values_by_parent is not None:
                raise ValueError(
                    f"enumerated mode level '{self.name}' cannot have both"
                    " values and values_by_parent"
                )
        return self


class Category(BaseModel):
    id: str
    label: str
    description: str
    fixed_levels: list[FixedLevel] = Field(default_factory=list)


class StageConfig(BaseModel):
    provider: Provider
    model: str
    max_tokens: int = Field(gt=0)


class PipelineConfig(BaseModel):
    stages: dict[str, StageConfig]


def _validate_values_by_parent_consistency(cats: list[Category]) -> None:
    """For each category with values_by_parent on level N, the keys must match
    the parent level's values[].id set exactly."""
    for cat in cats:
        levels = cat.fixed_levels
        for i, lvl in enumerate(levels):
            if lvl.values_by_parent is None:
                continue
            if i == 0:
                raise ValueError(
                    f"category {cat.id} level '{lvl.name}': values_by_parent"
                    " is invalid on the top level (no parent)"
                )
            parent = levels[i - 1]
            if parent.mode != "enumerated" or parent.values is None:
                raise ValueError(
                    f"category {cat.id} level '{lvl.name}': values_by_parent"
                    " requires parent level to be enumerated with flat values"
                )
            parent_ids = {v.id for v in parent.values}
            child_keys = set(lvl.values_by_parent.keys())
            if parent_ids != child_keys:
                missing = parent_ids - child_keys
                extra = child_keys - parent_ids
                raise ValueError(
                    f"category {cat.id} level '{lvl.name}': values_by_parent"
                    f" keys must match parent ids exactly. missing={sorted(missing)}"
                    f" extra={sorted(extra)}"
                )


def load_categories(path: Path) -> list[Category]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cats = [Category.model_validate(item) for item in data["categories"]]
    _validate_values_by_parent_consistency(cats)
    return cats


def load_pipeline(path: Path) -> PipelineConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PipelineConfig.model_validate(data)


def build_system_prompt(root: Path, stage_name: str) -> str:
    """Compose system prompt: shared domain + stage domain + pipeline rules."""
    parts: list[str] = []
    for candidate in (
        root / "config" / "domain.md",
        root / "config" / "domain" / f"{stage_name}.md",
    ):
        if candidate.exists():
            parts.append(candidate.read_text(encoding="utf-8").strip())
    rules = root / "pipeline" / "prompts" / f"{stage_name}.md"
    parts.append(rules.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts) + "\n"
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS — all 7 new tests + any existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/config.py tests/test_config.py
git commit -m "feat: add fixed_levels schema to Category model

Adds FixedLevel and LevelValue types supporting enumerated/open modes
and parent-dependent values (values_by_parent). Validation enforces
mode-field consistency and values_by_parent key uniqueness against
parent ids."
```

---

### Task 2: Manifest スキーマ拡張（新フィールド追加）

**Files:**
- Modify: `pipeline/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

`tests/test_state.py` に以下を追記:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — `consolidate` and `known_paths_cache` fields missing.

- [ ] **Step 3: Update `pipeline/state.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Manifest:
    raw: dict[str, dict[str, Any]] = field(default_factory=dict)
    snippets: dict[str, dict[str, Any]] = field(default_factory=dict)
    wiki: dict[str, dict[str, Any]] = field(default_factory=dict)
    consolidate: dict[str, dict[str, Any]] = field(default_factory=dict)
    known_paths_cache: dict[str, list[list[str]]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            raw=data.get("raw", {}),
            snippets=data.get("snippets", {}),
            wiki=data.get("wiki", {}),
            consolidate=data.get("consolidate", {}),
            known_paths_cache=data.get("known_paths_cache", {}),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "raw": self.raw,
                    "snippets": self.snippets,
                    "wiki": self.wiki,
                    "consolidate": self.consolidate,
                    "known_paths_cache": self.known_paths_cache,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `uv run pytest tests/test_state.py -v`
Expected: PASS — new tests pass, existing tests pass (backward compat preserved).

- [ ] **Step 5: Commit**

```bash
git add pipeline/state.py tests/test_state.py
git commit -m "feat: extend Manifest with consolidate and known_paths_cache

Adds two new fields for incremental execution support:
- consolidate: per-category path_frequency_hash for skip detection
- known_paths_cache: per-category cached path list for classify

Both load with empty defaults to keep existing manifests compatible."
```

---

### Task 3: 既存 categories.yaml に空 fixed_levels を追加

**Files:**
- Modify: `config/categories.yaml`

- [ ] **Step 1: Edit `config/categories.yaml`**

各カテゴリに `fixed_levels: []` を追加:

```yaml
categories:
  - id: 01-principles
    label: 原理原則
    description: ルール・ステージ・ブキ非依存の普遍理論
    fixed_levels: []
  - id: 02-rule-stage
    label: ルール×ステージ
    description: ルール×ステージ固有の定石
    fixed_levels: []
  - id: 03-weapon-role
    label: ブキ・役割
    description: ブキ／サブ／スペシャル／ロール固有のノウハウ（ギアパワー構成含む）
    fixed_levels: []
  - id: 04-stepup
    label: ステップアップガイド
    description: XP1800-2400 向けに ①②③ から抽出したエッセンス集
    fixed_levels: []
  - id: 05-glossary
    label: 用語集
    description: スプラトゥーン用語／FPS・TPS 用語
    fixed_levels: []
```

- [ ] **Step 2: Run all tests, verify nothing breaks**

Run: `uv run pytest -v`
Expected: PASS — fixed_levels: [] is loaded as empty list, existing pipeline behavior unchanged.

- [ ] **Step 3: Commit**

```bash
git add config/categories.yaml
git commit -m "chore: add empty fixed_levels to existing categories

Prepares categories.yaml for the path-based taxonomy. fixed_levels: []
means LLM decides everything (current behavior). Multi-level categories
(02 and 03) will be populated in a later commit."
```

---

## Phase 2: データモデル × ステージ更新（feature branch 推奨）

**重要**: ここから broken middle に入る。`feat/path-taxonomy` のような branch を切り、Task 14 完了まで main にマージしないこと。

### Task 4: Frontmatter モデルを path に変更

**Files:**
- Modify: `pipeline/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Update tests in `tests/test_models.py`**

既存テストの `subtopic="..."` を `path=[...]` に置換し、新規テストを追加:

```python
from datetime import UTC, datetime

import pytest

from pipeline.models import (
    ClassifiedFrontmatter,
    SnippetFrontmatter,
    WikiFrontmatter,
)


def test_classified_frontmatter_with_single_path() -> None:
    fm = ClassifiedFrontmatter(
        source_file="x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 1, tzinfo=UTC),
        content_hash="h1",
        category="01-principles",
        path=["dakai-fundamentals"],
    )
    assert fm.path == ["dakai-fundamentals"]


def test_classified_frontmatter_with_multi_level_path() -> None:
    fm = ClassifiedFrontmatter(
        source_file="x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 1, tzinfo=UTC),
        content_hash="h1",
        category="03-weapon-role",
        path=["シューター", "スプラシューター", "ギア構成"],
    )
    assert len(fm.path) == 3


def test_classified_frontmatter_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="path"):
        ClassifiedFrontmatter(
            source_file="x.md",
            source_date="2026-04-01",
            extracted_at=datetime(2026, 4, 1, tzinfo=UTC),
            content_hash="h1",
            category="01-principles",
            path=[],
        )


def test_wiki_frontmatter_with_path_and_merged_into() -> None:
    fm = WikiFrontmatter(
        title="x",
        category="01-principles",
        path=["dakai-fundamentals"],
        sources=[],
        updated_at=datetime(2026, 4, 1, tzinfo=UTC),
        tombstone=True,
        merged_into_path=["dakai-principles"],
        merged_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert fm.merged_into_path == ["dakai-principles"]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `subtopic` field still required, `path` field unknown.

- [ ] **Step 3: Update `pipeline/models.py`**

```python
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SnippetFrontmatter(BaseModel):
    source_file: str = Field(min_length=1)
    source_date: str = Field(min_length=1)
    extracted_at: datetime
    content_hash: str = Field(min_length=1)


class ClassifiedFrontmatter(SnippetFrontmatter):
    category: str = Field(min_length=1)
    path: list[str] = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def _no_empty_components(cls, v: list[str]) -> list[str]:
        for component in v:
            if not component or "/" in component:
                raise ValueError(
                    f"path component must be non-empty and not contain '/': {component!r}"
                )
        return v


class WikiFrontmatter(BaseModel):
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    path: list[str] = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    updated_at: datetime
    tombstone: bool = False
    merged_into_path: list[str] | None = None
    merged_at: datetime | None = None

    @field_validator("path")
    @classmethod
    def _no_empty_components(cls, v: list[str]) -> list[str]:
        for component in v:
            if not component or "/" in component:
                raise ValueError(
                    f"path component must be non-empty and not contain '/': {component!r}"
                )
        return v
```

- [ ] **Step 4: Run tests, verify the model tests pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS for new tests. **NOTE: stage tests will now be broken — this is expected and will be fixed in subsequent tasks.**

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py tests/test_models.py
git commit -m "feat!: replace subtopic with path in frontmatter models

BREAKING: ClassifiedFrontmatter.subtopic and WikiFrontmatter.subtopic
are removed. Use path: list[str] instead. WikiFrontmatter.merged_into
becomes merged_into_path: list[str] | None.

Stage code and tests will fail until subsequent tasks update them.
This commit is part of feat/path-taxonomy branch — do not merge to
main until Phase 2 is complete."
```

---

### Task 5: 既存 Splatoon データの 1 層 path 移行スクリプト

**Files:**
- Create: `scripts/migrate_to_path.py`
- Test: `tests/test_migrate_to_path.py`

- [ ] **Step 1: Write failing tests**

`tests/test_migrate_to_path.py` を新規作成:

```python
"""Tests for scripts/migrate_to_path.py.

The script converts legacy frontmatter (with `subtopic`) into the new
path-based schema. It edits files in place by manipulating frontmatter
strings — it does NOT round-trip through the new pydantic models (which
no longer accept `subtopic`).
"""

from datetime import UTC, datetime
from pathlib import Path

import frontmatter
import pytest

from scripts.migrate_to_path import migrate_workspace


def _write_legacy_classified(
    path: Path, category: str, subtopic: str, body: str = "本文"
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "source_file": "sample_raw/x.md",
        "source_date": "2026-04-01",
        "extracted_at": datetime(2026, 4, 1, tzinfo=UTC).isoformat(),
        "content_hash": "h1",
        "category": category,
        "subtopic": subtopic,
    }
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def _write_legacy_wiki(
    path: Path,
    category: str,
    subtopic: str,
    *,
    tombstone: bool = False,
    merged_into: str | None = None,
    body: str = "本文",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata: dict = {
        "title": "x",
        "category": category,
        "subtopic": subtopic,
        "sources": [],
        "updated_at": datetime(2026, 4, 1, tzinfo=UTC).isoformat(),
        "tombstone": tombstone,
    }
    if merged_into is not None:
        metadata["merged_into"] = merged_into
        metadata["merged_at"] = datetime(2026, 4, 1, tzinfo=UTC).isoformat()
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def test_migrates_classified_subtopic_to_path(tmp_path: Path) -> None:
    classified = tmp_path / "classified" / "01-principles" / "x.md"
    _write_legacy_classified(classified, "01-principles", "dakai-fundamentals")
    migrate_workspace(tmp_path)
    post = frontmatter.loads(classified.read_text(encoding="utf-8"))
    assert "subtopic" not in post.metadata
    assert post.metadata["path"] == ["dakai-fundamentals"]


def test_migrates_wiki_subtopic_to_path(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki" / "01-principles" / "dakai-fundamentals.md"
    _write_legacy_wiki(wiki, "01-principles", "dakai-fundamentals")
    migrate_workspace(tmp_path)
    post = frontmatter.loads(wiki.read_text(encoding="utf-8"))
    assert "subtopic" not in post.metadata
    assert post.metadata["path"] == ["dakai-fundamentals"]


def test_migrates_tombstone_merged_into(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki" / "01-principles" / "old-name.md"
    _write_legacy_wiki(
        wiki,
        "01-principles",
        "old-name",
        tombstone=True,
        merged_into="new-name",
    )
    migrate_workspace(tmp_path)
    post = frontmatter.loads(wiki.read_text(encoding="utf-8"))
    assert "merged_into" not in post.metadata
    assert post.metadata["merged_into_path"] == ["new-name"]


def test_migrates_manifest_classified_path(tmp_path: Path) -> None:
    classified = tmp_path / "classified" / "01-principles" / "x.md"
    _write_legacy_classified(classified, "01-principles", "dakai-fundamentals")
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"raw": {}, "snippets": {"snippets/x.md": {"source_hash": "h", "classified": true}}, "wiki": {}}\n',
        encoding="utf-8",
    )
    migrate_workspace(tmp_path)
    import json
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    # known_paths_cache populated for 01-principles
    assert "01-principles" in data["known_paths_cache"]
    assert data["known_paths_cache"]["01-principles"] == [["dakai-fundamentals"]]


def test_idempotent_when_already_migrated(tmp_path: Path) -> None:
    classified = tmp_path / "classified" / "01-principles" / "x.md"
    metadata = {
        "source_file": "sample_raw/x.md",
        "source_date": "2026-04-01",
        "extracted_at": datetime(2026, 4, 1, tzinfo=UTC).isoformat(),
        "content_hash": "h1",
        "category": "01-principles",
        "path": ["dakai-fundamentals"],
    }
    classified.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("本文", **metadata)
    classified.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    before = classified.read_text(encoding="utf-8")
    migrate_workspace(tmp_path)
    after = classified.read_text(encoding="utf-8")
    assert before == after  # no-op on already-migrated files
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_migrate_to_path.py -v`
Expected: FAIL — `scripts.migrate_to_path` module does not exist.

- [ ] **Step 3: Implement `scripts/migrate_to_path.py`**

```python
"""Migrate legacy subtopic-based frontmatter to path-based schema.

Usage:
    uv run python -m scripts.migrate_to_path [<workspace_root>]

Default workspace_root is the current working directory. The script:
1. Rewrites classified/*/*.md frontmatter (subtopic -> path: [subtopic])
2. Rewrites wiki/*/*.md frontmatter (subtopic -> path, merged_into -> merged_into_path)
3. Rebuilds state/ingest_manifest.json's known_paths_cache and adds
   classified_path entries to manifest.snippets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import frontmatter


def _migrate_frontmatter_file(path: Path) -> dict | None:
    """Migrate one .md file in place. Returns the new metadata dict (or None
    if the file had no frontmatter)."""
    text = path.read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    if not post.metadata:
        return None
    md = dict(post.metadata)
    changed = False

    if "subtopic" in md and "path" not in md:
        md["path"] = [md.pop("subtopic")]
        changed = True
    elif "subtopic" in md:
        # Both present? Trust path, drop legacy.
        del md["subtopic"]
        changed = True

    if "merged_into" in md and "merged_into_path" not in md:
        merged = md.pop("merged_into")
        md["merged_into_path"] = [merged] if merged is not None else None
        changed = True

    if changed:
        new_post = frontmatter.Post(post.content, **md)
        path.write_text(frontmatter.dumps(new_post) + "\n", encoding="utf-8")

    return md


def migrate_workspace(root: Path) -> None:
    classified_dir = root / "classified"
    wiki_dir = root / "wiki"
    manifest_path = root / "state" / "ingest_manifest.json"

    # 1. Migrate classified files; collect path data per category for cache.
    paths_by_cat: dict[str, list[list[str]]] = defaultdict(list)
    if classified_dir.exists():
        for f in sorted(classified_dir.rglob("*.md")):
            md = _migrate_frontmatter_file(f)
            if md is None:
                continue
            cat = md.get("category")
            path = md.get("path")
            if isinstance(cat, str) and isinstance(path, list):
                paths_by_cat[cat].append(list(path))

    # 2. Migrate wiki files (frontmatter only; file locations unchanged for 1-layer).
    if wiki_dir.exists():
        for f in sorted(wiki_dir.rglob("*.md")):
            _migrate_frontmatter_file(f)

    # 3. Rebuild manifest's known_paths_cache, add classified_path to each snippet.
    if not manifest_path.exists():
        return
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # known_paths_cache: deduplicate
    cache: dict[str, list[list[str]]] = {}
    for cat, plist in paths_by_cat.items():
        seen: list[list[str]] = []
        for p in plist:
            if p not in seen:
                seen.append(p)
        cache[cat] = sorted(seen)
    data["known_paths_cache"] = cache

    # classified_path on snippets: read from corresponding classified file
    snippets = data.get("snippets", {})
    for snippet_rel, entry in snippets.items():
        if not entry.get("classified"):
            continue
        if "classified_path" in entry:
            continue
        # Find the classified file matching this snippet name
        snippet_name = Path(snippet_rel).name
        for f in classified_dir.rglob(snippet_name):
            post = frontmatter.loads(f.read_text(encoding="utf-8"))
            p = post.metadata.get("path")
            if isinstance(p, list):
                entry["classified_path"] = list(p)
            break

    # consolidate field default
    data.setdefault("consolidate", {})

    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="migrate_to_path")
    p.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = p.parse_args(argv)
    migrate_workspace(args.root.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/__init__.py` を空ファイルで作成（`uv run python -m scripts.migrate_to_path` で動作させるため）:

```bash
mkdir -p scripts
touch scripts/__init__.py
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `uv run pytest tests/test_migrate_to_path.py -v`
Expected: PASS — all 5 migration tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_to_path.py scripts/__init__.py tests/test_migrate_to_path.py
git commit -m "feat: add migration script subtopic -> path

scripts/migrate_to_path.py rewrites classified/*/*.md and wiki/*/*.md
frontmatter from subtopic (str) to path ([str]). Tombstone files
get merged_into -> merged_into_path conversion. Manifest is updated
with known_paths_cache and per-snippet classified_path. Idempotent."
```

---

### Task 6: cluster ステージを path 対応に

**Files:**
- Modify: `pipeline/stages/cluster.py`
- Test: `tests/stages/test_cluster.py`

- [ ] **Step 1: Update tests**

`tests/stages/test_cluster.py` を読み、既存の `subtopic` ベースのテストを path ベースに更新:

```python
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.frontmatter_io import write_frontmatter
from pipeline.models import ClassifiedFrontmatter
from pipeline.stages import cluster
import json


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
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/stages/test_cluster.py -v`
Expected: FAIL — `cluster.py` still uses `fm.subtopic`.

- [ ] **Step 3: Update `pipeline/stages/cluster.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from pipeline.frontmatter_io import read_frontmatter
from pipeline.models import ClassifiedFrontmatter


def run(*, classified_dir: Path, clusters_path: Path) -> None:
    clusters: dict[str, list[str]] = {}

    for path in sorted(classified_dir.rglob("*.md")):
        fm, _ = read_frontmatter(path, ClassifiedFrontmatter)
        if fm is None:
            raise RuntimeError(f"unreachable: classified missing frontmatter: {path}")
        key = f"{fm.category}/{'/'.join(fm.path)}"
        rel = str(path.relative_to(classified_dir.parent))
        clusters.setdefault(key, []).append(rel)

    for key in clusters:
        clusters[key].sort()

    clusters_path.parent.mkdir(parents=True, exist_ok=True)
    clusters_path.write_text(
        json.dumps(clusters, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/stages/test_cluster.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/stages/cluster.py tests/stages/test_cluster.py
git commit -m "feat: update cluster stage to use path

Cluster keys are now category + '/'.join(path), supporting arbitrary
depth. No LLM changes."
```

---

### Task 7: classify ステージ — path 出力 + known_paths_cache 利用

**Files:**
- Modify: `pipeline/stages/classify.py`
- Modify: `pipeline/prompts/classify.md`
- Test: `tests/stages/test_classify.py`

- [ ] **Step 1: Update prompt `pipeline/prompts/classify.md`**

```markdown
スニペットを、固定されたカテゴリーと階層パス (path) に分類する。

入力として以下を受け取る:
- カテゴリーの一覧（id、ラベル、説明、固定層スキーマ）を YAML 形式で
- 既存の path 一覧（カテゴリ別、再利用候補）
- スニペット本文

タスク: カテゴリー ID を 1 つ選び、配下の階層パス (path) を決定する。

## 階層パス (path) について

各カテゴリは `fixed_levels` で 0 個以上の固定層を持つ:
- `mode: enumerated` の層: 入力の `values` または `values_by_parent` から
  必ず id（or label）の中から 1 つ選ぶ。それ以外は不可。
- `mode: open` の層: 既存 path に類似があれば再利用、なければ新規命名。
- `fixed_levels` 配下のさらに深い層は LLM が自由に追加できる（深さ可変）。
  既存 path を最大限再利用する。

path は最低 1 要素以上。各要素は `/` を含めない。

## 出力形式

JSON のみ、1 行で:
`{"category": "<category-id>", "path": ["<level0>", "<level1>", ...]}`

ルール:
- `category` は必ず提供された ID の中から選ぶ。
- enumerated 層では values の `id` をそのまま使う（`label` ではなく）。
- open 層・自由層は小文字ケバブケースまたは日本語可。
- 解説や前置き、コードブロックは出力に含めない。

## path 命名のルール（重要）

- 「**普遍的で長期的に成長しうる知識単位**」を表す名前にする
- **日付・個別事象・session 情報を含めない**
  - ❌ `["2026-04-26-general-dakai-home-base-clearing"]`
  - ✅ `["dakai-fundamentals"]`
- 既存 path に類似する内容なら、**必ず既存を再利用する**
- 迷ったら、最も近い既存 path を選ぶ
```

- [ ] **Step 2: Update tests in `tests/stages/test_classify.py`**

既存テストを置換 + 新規テストを追加:

```python
import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category, FixedLevel, LevelValue, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import ClassifiedFrontmatter, SnippetFrontmatter
from pipeline.stages import classify
from pipeline.state import Manifest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "snippets").mkdir()
    (tmp_path / "classified").mkdir()
    (tmp_path / "state").mkdir()
    return tmp_path


def _seed_snippet(workspace: Path, name: str, body: str) -> Path:
    path = workspace / "snippets" / name
    fm = SnippetFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
    )
    write_frontmatter(path, fm, body)
    return path


def test_classify_writes_path_to_classified(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "2026-04-01-abc.md", "右高台の制圧…")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        }
    ).save(manifest_path)

    categories = [
        Category(id="01-principles", label="原理原則", description="..."),
    ]
    provider = FakeLLMProvider(
        responses=[
            json.dumps({"category": "01-principles", "path": ["dakai-fundamentals"]})
        ]
    )

    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=categories,
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    out = workspace / "classified" / "01-principles" / "2026-04-01-abc.md"
    fm, _ = read_frontmatter(out, ClassifiedFrontmatter)
    assert fm.path == ["dakai-fundamentals"]


def test_classify_validates_enumerated_layer_id(workspace: Path) -> None:
    """When category has enumerated fixed level, the path[0] must be a known id."""
    snippet_path = _seed_snippet(workspace, "x.md", "本文")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        }
    ).save(manifest_path)

    categories = [
        Category(
            id="03-weapon-role",
            label="ブキ",
            description="x",
            fixed_levels=[
                FixedLevel(
                    name="ブキ種別",
                    mode="enumerated",
                    values=[LevelValue(id="shooter", label="シューター")],
                )
            ],
        )
    ]
    # LLM returns an unknown id "unknown-type" -> classify must reject
    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "03-weapon-role", "path": ["unknown-type"]})]
    )

    with pytest.raises(ValueError, match="enumerated"):
        classify.run(
            provider=provider,
            stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
            categories=categories,
            snippets_dir=workspace / "snippets",
            classified_dir=workspace / "classified",
            manifest_path=manifest_path,
            system_prompt="CLASSIFY PROMPT",
            root=workspace,
        )


def test_classify_uses_known_paths_cache_from_manifest(workspace: Path) -> None:
    """Existing classified paths are loaded from manifest cache, not by walking
    the classified dir."""
    snippet_path = _seed_snippet(workspace, "new.md", "新スニペット")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        },
        known_paths_cache={
            "01-principles": [["dakai-fundamentals"], ["frontline-fundamentals"]],
        },
    ).save(manifest_path)

    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "01-principles", "path": ["dakai-fundamentals"]})]
    )
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="原理原則", description="x")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    # The cache contents must appear in the user prompt
    user_prompt = provider.calls[0].user
    assert "dakai-fundamentals" in user_prompt
    assert "frontline-fundamentals" in user_prompt


def test_classify_appends_new_path_to_cache(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "new.md", "本文")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        }
    ).save(manifest_path)

    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "01-principles", "path": ["new-topic"]})]
    )
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="x", description="x")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    reloaded = Manifest.load(manifest_path)
    assert reloaded.known_paths_cache.get("01-principles") == [["new-topic"]]
    assert reloaded.snippets[str(snippet_path.relative_to(workspace))]["classified_path"] == [
        "new-topic"
    ]


def test_classify_skips_already_classified(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "x.md", "...")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": True,
            }
        }
    ).save(manifest_path)

    provider = FakeLLMProvider(responses=[])
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="x", description="x")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )
    assert provider.calls == []
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `uv run pytest tests/stages/test_classify.py -v`
Expected: FAIL — `path` field handling not implemented.

- [ ] **Step 4: Update `pipeline/stages/classify.py`**

```python
from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.config import Category, FixedLevel, StageConfig
from pipeline.frontmatter_io import write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter, SnippetFrontmatter
from pipeline.frontmatter_io import read_frontmatter
from pipeline.state import Manifest


def _enumerated_ids_at(level: FixedLevel, parent_id: str | None) -> set[str]:
    if level.values is not None:
        return {v.id for v in level.values}
    if level.values_by_parent is not None and parent_id is not None:
        return {v.id for v in level.values_by_parent.get(parent_id, [])}
    return set()


def _validate_path(category: Category, path: list[str]) -> None:
    """Raise ValueError if path violates fixed_levels mode constraints."""
    if not path:
        raise ValueError(f"classify returned empty path for category {category.id}")
    parent_id: str | None = None
    for i, level in enumerate(category.fixed_levels):
        if i >= len(path):
            raise ValueError(
                f"path is shorter than fixed_levels for category {category.id}: "
                f"path={path}, expected >= {len(category.fixed_levels)} components"
            )
        component = path[i]
        if level.mode == "enumerated":
            allowed = _enumerated_ids_at(level, parent_id)
            if component not in allowed:
                raise ValueError(
                    f"category {category.id} level '{level.name}' (enumerated): "
                    f"value {component!r} not in allowed ids {sorted(allowed)}"
                )
            parent_id = component
        else:
            # open level: any non-empty string ok (basic check already in pydantic)
            parent_id = None  # cannot drive child enumeration


def _build_user_prompt(
    categories: list[Category],
    snippet_body: str,
    known_paths: dict[str, list[list[str]]],
) -> str:
    cat_yaml = yaml.safe_dump(
        {"categories": [c.model_dump() for c in categories]},
        allow_unicode=True,
        sort_keys=False,
    )
    if known_paths:
        path_lines: list[str] = []
        for cat_id, paths in sorted(known_paths.items()):
            for p in sorted(paths):
                path_lines.append(f"- {cat_id}: {'/'.join(p)}")
        known_block = "\n".join(path_lines)
    else:
        known_block = "(まだなし)"
    return (
        f"{cat_yaml}\n\n"
        f"既存の path 一覧（カテゴリ別、適切な場合は再利用してください）:\n{known_block}\n\n"
        f"スニペット本文:\n---\n{snippet_body}\n---"
    )


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    snippets_dir: Path,
    classified_dir: Path,
    manifest_path: Path,
    system_prompt: str,
    root: Path,
) -> None:
    manifest = Manifest.load(manifest_path)
    valid_ids = {c.id for c in categories}
    cat_by_id = {c.id: c for c in categories}
    debug_dir = root / "state" / "debug"

    for snippet_path in sorted(snippets_dir.glob("*.md")):
        rel = str(snippet_path.relative_to(root))
        entry = manifest.snippets.get(rel)
        if entry and entry.get("classified"):
            continue

        fm, body = read_frontmatter(snippet_path, SnippetFrontmatter)
        if fm is None:
            raise RuntimeError(f"unreachable: snippet missing frontmatter: {snippet_path}")

        user = _build_user_prompt(categories, body, manifest.known_paths_cache)
        reply = provider.complete(
            system=system_prompt,
            user=user,
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="classify", debug_dir=debug_dir)
        category_id = parsed["category"]
        path = parsed["path"]

        if category_id not in valid_ids:
            raise ValueError(f"classify returned unknown category {category_id}")
        if not isinstance(path, list) or not path:
            raise ValueError(f"classify returned invalid path: {path!r}")
        _validate_path(cat_by_id[category_id], list(path))

        classified_fm = ClassifiedFrontmatter(
            **fm.model_dump(),
            category=category_id,
            path=path,
        )
        out = classified_dir / category_id / snippet_path.name
        write_frontmatter(out, classified_fm, body)

        # Update manifest
        entry = manifest.snippets.setdefault(
            rel, {"source_hash": fm.content_hash, "classified": False}
        )
        entry["classified"] = True
        entry["classified_path"] = list(path)

        cache_list = manifest.known_paths_cache.setdefault(category_id, [])
        if list(path) not in cache_list:
            cache_list.append(list(path))

    manifest.save(manifest_path)
```

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest tests/stages/test_classify.py -v`
Expected: PASS — all 5 tests.

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/classify.py pipeline/prompts/classify.md tests/stages/test_classify.py
git commit -m "feat: classify outputs path and uses known_paths_cache

Classify stage now:
- Outputs JSON {category, path: [...]}
- Validates enumerated layer values against config
- Uses manifest.known_paths_cache (avoids walking classified/)
- Updates cache and snippets[].classified_path on each new snippet"
```

---

### Task 8: compile ステージを path 対応に

**Files:**
- Modify: `pipeline/stages/compile.py`
- Test: `tests/stages/test_compile.py`

- [ ] **Step 1: Update tests in `tests/stages/test_compile.py`**

既存ヘルパー `_seed_classified` 等の `subtopic="..."` を `path=[...]` に置換。新規に多層パスのテストを追加:

```python
def test_compile_writes_leaf_to_nested_path(workspace: Path) -> None:
    """Multi-level path produces nested wiki/<cat>/<l0>/<l1>/<leaf>.md output."""
    classified_path = workspace / "classified" / "03-weapon-role" / "x.md"
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 1),
        content_hash="h1",
        category="03-weapon-role",
        path=["シューター", "スプラシューター", "ギア構成"],
    )
    classified_path.parent.mkdir(parents=True, exist_ok=True)
    write_frontmatter(classified_path, fm, "本文")

    clusters_path = workspace / "state" / "clusters.json"
    clusters_path.parent.mkdir(parents=True, exist_ok=True)
    clusters_path.write_text(
        json.dumps(
            {
                "03-weapon-role/シューター/スプラシューター/ギア構成": [
                    "classified/03-weapon-role/x.md"
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest().save(manifest_path)

    provider = FakeLLMProvider(
        responses=[json.dumps({"title": "ギア構成", "body": "本文"})]
    )
    compile_stage.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=[
            Category(id="03-weapon-role", label="ブキ", description="x"),
        ],
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        clusters_path=clusters_path,
        manifest_path=manifest_path,
        system_prompt="x",
        source_urls={},
        root=workspace,
    )

    out = (
        workspace / "wiki" / "03-weapon-role" / "シューター" / "スプラシューター" / "ギア構成.md"
    )
    assert out.exists()
    written, _ = read_frontmatter(out, WikiFrontmatter)
    assert written.path == ["シューター", "スプラシューター", "ギア構成"]
```

既存の単一階層テストは `path=["<value>"]` 形式に書き換える。出力先は `wiki/<cat>/<value>.md` のままで OK（path=[<v>] の場合の振る舞い）。

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/stages/test_compile.py -v`
Expected: FAIL — compile uses subtopic.

- [ ] **Step 3: Update `pipeline/stages/compile.py`**

主な変更点:
- `category_id, subtopic = key.split("/", 1)` → `category_id, *path = key.split("/")`
- `wiki_rel = f"wiki/{category_id}/{subtopic}.md"` → `wiki_rel = f"wiki/{category_id}/{'/'.join(path)}.md"`
- `wiki_dir / category_id / f"{subtopic}.md"` → `wiki_dir / category_id / Path(*path).with_suffix(".md")`
- `WikiFrontmatter(... subtopic=subtopic ...)` → `WikiFrontmatter(... path=path ...)`

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import Category, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.state import Manifest


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _fingerprint(paths: list[str]) -> str:
    joined = "\n".join(sorted(paths))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _load_snippets(root: Path, paths: list[str]) -> tuple[list[str], set[str]]:
    bodies: list[str] = []
    source_files: set[str] = set()
    for rel in paths:
        fm, body = read_frontmatter(root / rel, ClassifiedFrontmatter)
        if fm is None:
            raise RuntimeError(f"unreachable: classified missing frontmatter: {rel}")
        bodies.append(body.strip())
        source_files.add(fm.source_file)
    return bodies, source_files


def _build_user_prompt(category_label: str, path: list[str], bodies: list[str]) -> str:
    numbered = "\n\n".join(f"{i + 1}. {b}" for i, b in enumerate(bodies))
    path_str = " > ".join(path)
    return f"カテゴリー: {category_label}\nパス: {path_str}\n\nスニペット:\n{numbered}"


def _with_sources(body: str, sources: list[str]) -> str:
    if not sources:
        return body.rstrip() + "\n"
    lines = ["", "## 出典", ""]
    for url in sources:
        lines.append(f"- {url}")
    lines.append("")
    return body.rstrip() + "\n\n" + "\n".join(lines)


def _wiki_output_path(wiki_dir: Path, category_id: str, path: list[str]) -> Path:
    return wiki_dir / category_id / Path(*path).with_suffix(".md")


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    classified_dir: Path,
    wiki_dir: Path,
    clusters_path: Path,
    manifest_path: Path,
    system_prompt: str,
    source_urls: dict[str, str],
    now: Callable[[], datetime] = _now_utc,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))
    manifest = Manifest.load(manifest_path)
    label_by_id = {c.id: c.label for c in categories}
    debug_dir = root / "state" / "debug"

    for key, paths in clusters.items():
        category_id, *path_components = key.split("/")
        if not path_components:
            raise ValueError(f"compile: cluster key has no path: {key!r}")
        out_path = _wiki_output_path(wiki_dir, category_id, path_components)
        wiki_rel = str(out_path.relative_to(root))
        fingerprint = _fingerprint(paths)

        prior = manifest.wiki.get(wiki_rel, {}).get("cluster_fingerprint")
        if prior == fingerprint:
            continue

        bodies, source_files = _load_snippets(root, paths)
        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(label_by_id[category_id], path_components, bodies),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="compile", debug_dir=debug_dir)
        title = parsed["title"]
        body = parsed["body"]

        sources = sorted(source_urls[s] for s in source_files if s in source_urls)
        final_body = _with_sources(body, sources)
        updated_at = now()

        fm = WikiFrontmatter(
            title=title,
            category=category_id,
            path=path_components,
            sources=sources,
            updated_at=updated_at,
        )
        write_frontmatter(out_path, fm, final_body)

        manifest.wiki[wiki_rel] = {"cluster_fingerprint": fingerprint}

    manifest.save(manifest_path)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/stages/test_compile.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/stages/compile.py tests/stages/test_compile.py
git commit -m "feat: compile stage emits leaves at nested wiki paths

Cluster key is now category + '/'.join(path). Output goes to
wiki/<cat>/<l0>/<l1>/.../<leaf>.md. WikiFrontmatter.path stores
the full path."
```

---

### Task 9: consolidate ステージ — path 対応 + カテゴリ単位スキップ

**Files:**
- Modify: `pipeline/stages/consolidate.py`
- Modify: `pipeline/prompts/consolidate.md`
- Test: `tests/stages/test_consolidate.py`

- [ ] **Step 1: Update prompt `pipeline/prompts/consolidate.md`**

```markdown
あなたは Wiki の path 一覧を見て、統合や改名が必要かを判断する。

入力:
- カテゴリ ID
- 現在の path 一覧（path 配列、各 path に属する snippet 数つき）
- 各層の mode（enumerated か open か）

タスク: 統合や改名すべき path を判定し、rename map を返す。

## 重要な制約

- **enumerated 層は YAML が真実なので一切変更しない**。enumerated 層を含む rename
  提案は絶対に出さない。`from_path` と `to_path` で **enumerated 層の値が同一** で
  なければならない。
- 変更対象は **open 層と固定層を超えた自由層のみ**。

## 統合・改名が望ましい強い基準

- 明らかに同じ概念を別名で呼んでいる
  （例: `["dakai-fundamentals"]` と `["dakai-principles"]`）
- 一方が他方の完全な部分集合で、独立した粒度を持たない
- 日付や個別事象を含む path 要素が、既存の汎用 path に明確に該当する
- 多層 path の終端（末尾要素）の重複・類似

## 統合してはいけない弱い基準

- 「似ている気がする」程度の主観的判断
- 概念の重複が部分的にしかない
- 統合先の wiki ページが大きくなりすぎる懸念がある
- 判断に迷う

迷ったら「変更なし」を選ぶ。Wiki の安定性は変更の活発さより重要。

## 出力形式

JSON のみ、1 行で:
`{"renames": [{"category": "<id>", "from_path": [...], "to_path": [...], "reason": "<1 文>"}]}`

統合・改名が不要な場合は `{"renames": []}` を返す。

解説や前置き、コードフェンスは出力に含めない。
```

- [ ] **Step 2: Update tests in `tests/stages/test_consolidate.py`**

ヘルパーを path ベースに書き換え + 新規テストを追加:

```python
import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category, FixedLevel, LevelValue, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.stages import consolidate
from pipeline.state import Manifest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "classified").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "state").mkdir()
    return tmp_path


def _seed_classified(
    workspace: Path, category: str, name: str, path: list[str], body: str = "本文"
) -> Path:
    file_path = workspace / "classified" / category / name
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
        category=category,
        path=path,
    )
    write_frontmatter(file_path, fm, body)
    return file_path


def _categories_principles_only() -> list[Category]:
    return [Category(id="01-principles", label="原理原則", description="x")]


def test_consolidate_skips_when_path_frequency_unchanged(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "x.md", ["dakai-fundamentals"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    # First run: hash unset, LLM is called
    provider = FakeLLMProvider(responses=[json.dumps({"renames": []})])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )
    assert len(provider.calls) == 1

    # Second run: hash matches, LLM is NOT called
    provider = FakeLLMProvider(responses=[])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )
    assert provider.calls == []


def test_consolidate_calls_llm_when_path_frequency_changes(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "x.md", ["dakai-fundamentals"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    # First run
    consolidate.run(
        provider=FakeLLMProvider(responses=[json.dumps({"renames": []})]),
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )

    # Add a new path
    _seed_classified(workspace, "01-principles", "y.md", ["new-topic"])

    # Second run: hash differs, LLM is called
    provider = FakeLLMProvider(responses=[json.dumps({"renames": []})])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )
    assert len(provider.calls) == 1


def test_consolidate_applies_path_rename(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "x.md", ["old-name"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "renames": [
                        {
                            "category": "01-principles",
                            "from_path": ["old-name"],
                            "to_path": ["new-name"],
                            "reason": "テスト",
                        }
                    ]
                }
            )
        ]
    )
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=_categories_principles_only(),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )

    out = workspace / "classified" / "01-principles" / "x.md"
    fm, _ = read_frontmatter(out, ClassifiedFrontmatter)
    assert fm.path == ["new-name"]


def test_consolidate_rejects_rename_changing_enumerated_layer(workspace: Path) -> None:
    _seed_classified(workspace, "03-weapon-role", "x.md", ["shooter", "splash-shooter"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    categories = [
        Category(
            id="03-weapon-role",
            label="ブキ",
            description="x",
            fixed_levels=[
                FixedLevel(
                    name="ブキ種別",
                    mode="enumerated",
                    values=[
                        LevelValue(id="shooter", label="シューター"),
                        LevelValue(id="roller", label="ローラー"),
                    ],
                ),
                FixedLevel(
                    name="個別ブキ",
                    mode="enumerated",
                    values_by_parent={
                        "shooter": [LevelValue(id="splash-shooter", label="スプラ")],
                        "roller": [LevelValue(id="splat-roller", label="スプラローラー")],
                    },
                ),
            ],
        )
    ]
    # LLM proposes changing the enumerated layer 0 (shooter -> roller); must be rejected
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "renames": [
                        {
                            "category": "03-weapon-role",
                            "from_path": ["shooter", "splash-shooter"],
                            "to_path": ["roller", "splat-roller"],
                            "reason": "x",
                        }
                    ]
                }
            )
        ]
    )
    with pytest.raises(ValueError, match="enumerated"):
        consolidate.run(
            provider=provider,
            stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
            categories=categories,
            classified_dir=workspace / "classified",
            wiki_dir=workspace / "wiki",
            log_path=workspace / "state" / "consolidate_log.md",
            manifest_path=manifest_path,
            system_prompt="x",
            now=lambda: datetime(2026, 4, 30),
            root=workspace,
        )


def test_consolidate_skips_enumerated_only_categories(workspace: Path) -> None:
    """If a category's fixed_levels are all enumerated and no free tail exists,
    consolidate skips it entirely (no LLM call)."""
    _seed_classified(workspace, "03-weapon-role", "x.md", ["shooter", "splash-shooter"])
    manifest_path = workspace / "state" / "ingest_manifest.json"

    categories = [
        Category(
            id="03-weapon-role",
            label="ブキ",
            description="x",
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
                        "shooter": [LevelValue(id="splash-shooter", label="スプラ")]
                    },
                ),
            ],
        )
    ]
    provider = FakeLLMProvider(responses=[])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        categories=categories,
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        manifest_path=manifest_path,
        system_prompt="x",
        now=lambda: datetime(2026, 4, 30),
        root=workspace,
    )
    assert provider.calls == []
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `uv run pytest tests/stages/test_consolidate.py -v`
Expected: FAIL — consolidate uses subtopic, no skip logic, no enumerated-only detection.

- [ ] **Step 4: Update `pipeline/stages/consolidate.py`**

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.config import Category, FixedLevel, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.state import Manifest


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _collect_path_frequencies(classified_dir: Path) -> dict[str, dict[tuple[str, ...], int]]:
    """Return {category_id: {path_tuple: snippet_count}} for non-empty categories."""
    by_cat: dict[str, dict[tuple[str, ...], int]] = {}
    for cat_dir in sorted(classified_dir.glob("*/")):
        cat_id = cat_dir.name
        counts: dict[tuple[str, ...], int] = {}
        for path in sorted(cat_dir.glob("*.md")):
            fm, _ = read_frontmatter(path, ClassifiedFrontmatter)
            if fm is None:
                raise RuntimeError(f"unreachable: classified missing frontmatter: {path}")
            key = tuple(fm.path)
            counts[key] = counts.get(key, 0) + 1
        if counts:
            by_cat[cat_id] = counts
    return by_cat


def _hash_frequency_map(freq_map: dict[tuple[str, ...], int]) -> str:
    canonical = sorted((list(p), c) for p, c in freq_map.items())
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _has_free_tail(category: Category, freq_map: dict[tuple[str, ...], int]) -> bool:
    """True if any path in freq_map extends beyond fixed_levels."""
    fixed_depth = len(category.fixed_levels)
    return any(len(p) > fixed_depth for p in freq_map)


def _all_levels_enumerated(category: Category) -> bool:
    return bool(category.fixed_levels) and all(
        lvl.mode == "enumerated" for lvl in category.fixed_levels
    )


def _build_user_prompt(
    category: Category, freq_map: dict[tuple[str, ...], int]
) -> str:
    lines = [f"カテゴリ: {category.id}", ""]
    if category.fixed_levels:
        lines.append("固定層:")
        for i, lvl in enumerate(category.fixed_levels):
            lines.append(f"  {i}: {lvl.name} ({lvl.mode})")
        lines.append("")
    lines.append("現在の path 一覧 (snippet 数):")
    for path_tuple, count in sorted(freq_map.items()):
        lines.append(f"- {list(path_tuple)} : {count}")
    return "\n".join(lines)


def _validate_rename(
    rename: dict[str, Any],
    cat_by_id: dict[str, Category],
    available: dict[str, dict[tuple[str, ...], int]],
) -> None:
    cat_id = rename.get("category")
    src = rename.get("from_path")
    dst = rename.get("to_path")
    if not isinstance(cat_id, str) or not isinstance(src, list) or not isinstance(dst, list):
        raise ValueError(f"consolidate: malformed rename entry: {rename!r}")
    if cat_id not in cat_by_id:
        raise ValueError(f"consolidate: unknown category in rename: {cat_id!r}")
    if cat_id not in available or tuple(src) not in available[cat_id]:
        raise ValueError(
            f"consolidate: unknown source path in rename: {cat_id}/{src}"
        )

    # Reject if any enumerated layer differs between from_path and to_path
    cat = cat_by_id[cat_id]
    for i, lvl in enumerate(cat.fixed_levels):
        if lvl.mode != "enumerated":
            continue
        src_v = src[i] if i < len(src) else None
        dst_v = dst[i] if i < len(dst) else None
        if src_v != dst_v:
            raise ValueError(
                f"consolidate: rename cannot change enumerated layer "
                f"'{lvl.name}': {src_v!r} -> {dst_v!r}"
            )


def _rewrite_classified_path(
    classified_dir: Path, category: str, src: list[str], dst: list[str]
) -> None:
    cat_dir = classified_dir / category
    for path in sorted(cat_dir.glob("*.md")):
        fm, body = read_frontmatter(path, ClassifiedFrontmatter)
        if fm is None or list(fm.path) != list(src):
            continue
        new_fm = ClassifiedFrontmatter(**{**fm.model_dump(), "path": list(dst)})
        write_frontmatter(path, new_fm, body)


def _tombstone_wiki_page(
    wiki_dir: Path,
    category: str,
    src: list[str],
    dst: list[str],
    reason: str,
    now: datetime,
) -> None:
    old_wiki = wiki_dir / category / Path(*src).with_suffix(".md")
    if not old_wiki.exists():
        return
    src_label = "/".join(src)
    dst_label = "/".join(dst)
    tombstone_fm = WikiFrontmatter(
        title=f"統合済み: {src_label}",
        category=category,
        path=src,
        sources=[],
        updated_at=now,
        tombstone=True,
        merged_into_path=dst,
        merged_at=now,
    )
    body_lines = [
        f"# 統合済み: {src_label}",
        "",
        f"このページは [{dst_label}](../{Path(*dst).with_suffix('.md').as_posix()}) に統合されました。",
    ]
    if reason:
        body_lines.append("")
        body_lines.append(f"統合理由: {reason}")
    write_frontmatter(old_wiki, tombstone_fm, "\n".join(body_lines) + "\n")


def _append_log(log_path: Path, renames: list[dict[str, Any]], now: datetime) -> None:
    if not renames:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"## {now.isoformat()}",
        "",
        f"{len(renames)} 件の path を統合した。",
        "",
    ]
    for r in renames:
        cat = r["category"]
        src_label = "/".join(r["from_path"])
        dst_label = "/".join(r["to_path"])
        lines.append(f"- `{cat}/{src_label}` → `{cat}/{dst_label}`")
        reason = r.get("reason")
        if reason:
            lines.append(f"  - 理由: {reason}")
    lines.append("")
    lines.append("---")
    lines.append("")
    new_block = "\n".join(lines)
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(existing + new_block, encoding="utf-8")


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    classified_dir: Path,
    wiki_dir: Path,
    log_path: Path,
    manifest_path: Path,
    system_prompt: str,
    now: Callable[[], datetime] = _now_utc,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    debug_dir = root / "state" / "debug"

    manifest = Manifest.load(manifest_path)
    cat_by_id = {c.id: c for c in categories}

    by_cat = _collect_path_frequencies(classified_dir)
    if not by_cat:
        return

    all_renames: list[dict[str, Any]] = []
    for cat_id, freq_map in by_cat.items():
        cat = cat_by_id.get(cat_id)
        if cat is None:
            continue

        # Skip if all fixed_levels are enumerated AND no free tail exists.
        if _all_levels_enumerated(cat) and not _has_free_tail(cat, freq_map):
            continue

        new_hash = _hash_frequency_map(freq_map)
        prior = manifest.consolidate.get(cat_id, {}).get("path_frequency_hash")
        if prior == new_hash:
            continue

        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(cat, freq_map),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="consolidate", debug_dir=debug_dir)
        renames = parsed.get("renames", [])
        for r in renames:
            _validate_rename(r, cat_by_id, by_cat)
        all_renames.extend(renames)

        manifest.consolidate[cat_id] = {
            "path_frequency_hash": new_hash,
            "last_run_at": now().isoformat(),
        }

    if all_renames:
        ts = now()
        for r in all_renames:
            cat_id = r["category"]
            src = list(r["from_path"])
            dst = list(r["to_path"])
            reason = r.get("reason", "")
            _rewrite_classified_path(classified_dir, cat_id, src, dst)
            _tombstone_wiki_page(wiki_dir, cat_id, src, dst, reason, ts)
        _append_log(log_path, all_renames, ts)

    # known_paths_cache is rebuilt from the new state of classified/
    refreshed = _collect_path_frequencies(classified_dir)
    manifest.known_paths_cache = {
        cat_id: sorted(list(p) for p in fm.keys())
        for cat_id, fm in refreshed.items()
    }
    manifest.save(manifest_path)
```

注意: `consolidate.run` のシグネチャに `manifest_path` を追加した。`pipeline/main.py` 側の呼び出しも合わせて修正が必要（次タスクで対応 — 一旦ここでは更新する）:

`pipeline/main.py` の consolidate 呼び出しを以下に変更:
```python
elif name == "consolidate":
    stage_cfg = pipeline_cfg.stages["consolidate"]
    consolidate.run(
        provider=get_provider(stage_cfg),
        stage_cfg=stage_cfg,
        categories=categories,
        classified_dir=root / "classified",
        wiki_dir=root / "wiki",
        log_path=root / "state" / "consolidate_log.md",
        manifest_path=root / "state" / "ingest_manifest.json",
        system_prompt=build_system_prompt(root, "consolidate"),
        root=root,
    )
```

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest tests/stages/test_consolidate.py tests/test_main_cli.py -v`
Expected: PASS for consolidate tests; some test_main_cli tests may need fix-ups for the new manifest_path arg (handled by main.py update above).

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/consolidate.py pipeline/prompts/consolidate.md pipeline/main.py tests/stages/test_consolidate.py
git commit -m "feat: consolidate uses path frequency hash and skips enumerated-only

- LLM is invoked only when a category's path frequency map changes
- enumerated-only categories (no free tail) skip entirely
- Renames are rejected if they change any enumerated layer value
- Output JSON now uses from_path / to_path (lists) instead of from / to
- known_paths_cache is rebuilt at end of run"
```

---

### Task 10: index ステージを再帰化

**Files:**
- Modify: `pipeline/stages/index.py`
- Test: `tests/stages/test_index.py`

- [ ] **Step 1: Update tests**

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline.config import Category
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.models import WikiFrontmatter
from pipeline.stages import index


def _seed_wiki(
    wiki_dir: Path,
    category: str,
    path: list[str],
    *,
    title: str = "ページタイトル",
    body: str = "概要文。",
    tombstone: bool = False,
) -> Path:
    out = wiki_dir / category / Path(*path).with_suffix(".md")
    fm = WikiFrontmatter(
        title=title,
        category=category,
        path=path,
        sources=[],
        updated_at=datetime(2026, 4, 30, tzinfo=UTC),
        tombstone=tombstone,
    )
    write_frontmatter(out, fm, body)
    return out


def test_index_writes_top_readme(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(wiki_dir, "01-principles", ["dakai-fundamentals"])
    cats = [Category(id="01-principles", label="原理原則", description="x")]
    index.run(wiki_dir=wiki_dir, categories=cats)
    top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    assert "01-principles" in top


def test_index_writes_intermediate_readme_for_multi_level(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(wiki_dir, "03-weapon-role", ["シューター", "スプラシューター", "ギア構成"])
    _seed_wiki(wiki_dir, "03-weapon-role", ["シューター", "ボールドマーカー", "立ち回り"])
    cats = [Category(id="03-weapon-role", label="ブキ", description="x")]
    index.run(wiki_dir=wiki_dir, categories=cats)

    # Intermediate README at <cat>/<l0>/README.md
    shooter_readme = (wiki_dir / "03-weapon-role" / "シューター" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "スプラシューター" in shooter_readme
    assert "ボールドマーカー" in shooter_readme

    # Intermediate README at <cat>/<l0>/<l1>/README.md
    splash_readme = (
        wiki_dir / "03-weapon-role" / "シューター" / "スプラシューター" / "README.md"
    ).read_text(encoding="utf-8")
    assert "ギア構成" in splash_readme


def test_index_excludes_tombstones_from_listing(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(wiki_dir, "01-principles", ["alive-page"])
    _seed_wiki(wiki_dir, "01-principles", ["dead-page"], tombstone=True)
    cats = [Category(id="01-principles", label="原理原則", description="x")]
    index.run(wiki_dir=wiki_dir, categories=cats)
    cat_readme = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")
    assert "alive-page" in cat_readme
    assert "dead-page" not in cat_readme


def test_index_no_llm_calls(tmp_path: Path) -> None:
    """Sanity: index ステージは LLM を一切呼ばない。"""
    # If implementation accidentally takes a provider, signature mismatch raises early.
    # Otherwise this test simply confirms run() works without provider parameter.
    wiki_dir = tmp_path / "wiki"
    _seed_wiki(wiki_dir, "01-principles", ["x"])
    index.run(wiki_dir=wiki_dir, categories=[Category(id="01-principles", label="y", description="z")])
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/stages/test_index.py -v`
Expected: FAIL — intermediate README generation not implemented.

- [ ] **Step 3: Update `pipeline/stages/index.py`**

```python
from __future__ import annotations

from pathlib import Path

from pipeline.config import Category
from pipeline.frontmatter_io import read_frontmatter
from pipeline.models import WikiFrontmatter

_NO_BODY = "(本文なし)"
_PARAGRAPH_BREAK_PREFIXES = ("#", "-", "*", ">", "|", "```")
_SUMMARY_MAX_CHARS = 120


def _extract_summary(body: str) -> str:
    lines = body.splitlines()
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("## ", "# ")):
            start = i + 1
            break

    paragraph_lines: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(_PARAGRAPH_BREAK_PREFIXES):
            if paragraph_lines:
                break
            continue
        paragraph_lines.append(stripped)

    if not paragraph_lines:
        return _NO_BODY

    paragraph = " ".join(paragraph_lines)
    sentence = paragraph
    for idx, ch in enumerate(paragraph):
        if ch == "。":
            sentence = paragraph[: idx + 1]
            break
        if ch == "." and (idx + 1 >= len(paragraph) or paragraph[idx + 1].isspace()):
            sentence = paragraph[: idx + 1]
            break

    if len(sentence) > _SUMMARY_MAX_CHARS:
        sentence = sentence[:_SUMMARY_MAX_CHARS] + "…"
    return sentence


def _is_excluded(p: Path) -> bool:
    """README.md is excluded; tombstone leaves are excluded."""
    if p.name == "README.md":
        return True
    fm, _ = read_frontmatter(p, WikiFrontmatter, require=False)
    if fm is not None and fm.tombstone:
        return True
    return False


def _list_subdirectories(d: Path) -> list[Path]:
    return sorted([p for p in d.iterdir() if p.is_dir()])


def _list_leaf_pages(d: Path) -> list[Path]:
    return sorted([p for p in d.glob("*.md") if not _is_excluded(p)])


def _write_intermediate_readme(
    dir_path: Path, breadcrumb: list[str], category_label: str
) -> None:
    """Write a static index README for an intermediate node."""
    title = breadcrumb[-1] if breadcrumb else category_label
    crumb = " > ".join(breadcrumb) if breadcrumb else category_label
    lines = [f"# {title}", "", f"`{category_label} > {crumb}`" if breadcrumb else f"`{category_label}`", ""]

    subdirs = _list_subdirectories(dir_path)
    if subdirs:
        lines.append("## サブカテゴリ")
        lines.append("")
        for sub in subdirs:
            lines.append(f"- [{sub.name}/]({sub.name}/)")
        lines.append("")

    leaves = _list_leaf_pages(dir_path)
    if leaves:
        lines.append("## ページ")
        lines.append("")
        for leaf in leaves:
            fm, body = read_frontmatter(leaf, WikiFrontmatter)
            if fm is None:
                continue
            summary = _extract_summary(body)
            lines.append(f"- [{fm.title}]({leaf.name}) — {summary}")
        lines.append("")

    if not subdirs and not leaves:
        lines.append("(まだページがありません)")
        lines.append("")

    (dir_path / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _write_recursive(dir_path: Path, breadcrumb: list[str], category_label: str) -> None:
    if not dir_path.is_dir():
        return
    _write_intermediate_readme(dir_path, breadcrumb, category_label)
    for sub in _list_subdirectories(dir_path):
        _write_recursive(sub, breadcrumb + [sub.name], category_label)


def _count_leaf_pages_recursive(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    count = len(_list_leaf_pages(dir_path))
    for sub in _list_subdirectories(dir_path):
        count += _count_leaf_pages_recursive(sub)
    return count


def _write_top_readme(wiki_dir: Path, categories: list[Category], counts: dict[str, int]) -> None:
    lines = [
        "# Splatoon 3 Wiki",
        "",
        "LLM が生成・編纂したナレッジ集。",
        "",
        "## カテゴリ",
        "",
    ]
    for cat in categories:
        count = counts.get(cat.id, 0)
        lines.append(f"- [{cat.id}]({cat.id}/) — {cat.label} — {count} ページ")
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(*, wiki_dir: Path, categories: list[Category]) -> None:
    """Generate static README.md at every wiki tree node (top, category, intermediates)."""
    counts: dict[str, int] = {}
    for cat in categories:
        cat_dir = wiki_dir / cat.id
        counts[cat.id] = _count_leaf_pages_recursive(cat_dir)
        _write_recursive(cat_dir, [], cat.label)
    _write_top_readme(wiki_dir, categories, counts)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/stages/test_index.py -v`
Expected: PASS — all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/stages/index.py tests/stages/test_index.py
git commit -m "feat: index stage emits recursive static READMEs

Each intermediate directory under wiki/<category>/ now gets a static
README.md listing its subcategories and direct leaf pages. Tombstones
are excluded. No LLM calls."
```

---

### Task 11: E2E テストを path 対応に更新

**Files:**
- Modify: `tests/test_end_to_end.py`

注: `tests/stages/test_ingest.py` は ingest が `SnippetFrontmatter`（path / subtopic を持たない）のみを生成するため変更不要。確認のためだけに `grep -n "subtopic" tests/stages/test_ingest.py` を実行し、ヒットがないことを確かめる。

- [ ] **Step 1: Update existing E2E test to use path**

`tests/test_end_to_end.py` の既存の `test_pipeline_end_to_end_with_fake_llm` を以下に置換（変更点: classify レスポンスを `subtopic` から `path` に、index ステージ呼び出しを追加、consolidate に `manifest_path` 引数を追加、wiki ファイルパスは 1-layer なので変わらず）:

```python
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

    (root / "sample_raw" / "2026-04-01-notes.md").write_text(
        "右高台の話など。", encoding="utf-8"
    )
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
        responses=[
            json.dumps({"category": "02-rule-stage", "path": ["海女美術-ガチエリア"]})
        ]
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
    # Top README and category README exist
    assert (root / "wiki" / "README.md").exists()
    assert (root / "wiki" / "02-rule-stage" / "README.md").exists()
```

- [ ] **Step 2: Add multi-level path E2E test**

同ファイル末尾に追加:

```python
def test_pipeline_end_to_end_multi_level_path(tmp_path: Path) -> None:
    """E2E with a 3-layer path: 03-weapon-role/シューター/スプラシューター/ギア構成."""
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
                        "shooter": [
                            LevelValue(id="splash-shooter", label="スプラシューター")
                        ]
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
        provider=FakeLLMProvider(
            responses=[json.dumps({"renames": []}, ensure_ascii=False)]
        ),
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

    # Leaf at the deepest path
    leaf = root / "wiki" / "03-weapon-role" / "shooter" / "splash-shooter" / "ギア構成.md"
    assert leaf.exists()
    # Intermediate README at every level
    assert (root / "wiki" / "03-weapon-role" / "README.md").exists()
    assert (root / "wiki" / "03-weapon-role" / "shooter" / "README.md").exists()
    assert (
        root / "wiki" / "03-weapon-role" / "shooter" / "splash-shooter" / "README.md"
    ).exists()
    # The intermediate README should reference the leaf
    splash_readme = (
        root / "wiki" / "03-weapon-role" / "shooter" / "splash-shooter" / "README.md"
    ).read_text(encoding="utf-8")
    assert "ギア構成" in splash_readme
```

- [ ] **Step 3: Run E2E tests, verify pass**

Run: `uv run pytest tests/test_end_to_end.py -v`
Expected: PASS — both tests.

- [ ] **Step 4: Run full test suite to ensure Phase 2 closure**

Run: `uv run pytest -v`
Expected: PASS — entire suite green. **Phase 2 closure: data model migration complete, all stages on path schema.**

- [ ] **Step 5: Verify lint and format are clean**

```bash
uv run ruff check .
uv run ruff format --check .
```

Expected: 両方ともエラーゼロ。

- [ ] **Step 6: Commit**

```bash
git add tests/test_end_to_end.py
git commit -m "test: E2E coverage for path schema, single + multi-level

Updates the existing single-layer E2E to use path: [...]. Adds new
multi-level E2E (03-weapon-role/shooter/splash-shooter/ギア構成)
that verifies nested wiki output and recursive intermediate READMEs.
Closes Phase 2."
```

---

## Phase 3: CLI `--rebuild` フラグ

### Task 12: `--rebuild` フラグの実装

**Files:**
- Modify: `pipeline/main.py`
- Test: `tests/test_main_cli.py`

- [ ] **Step 1: Write failing tests**

`tests/test_main_cli.py` に追記:

```python
def test_rebuild_all_clears_full_manifest(tmp_path: Path, monkeypatch) -> None:
    """--all --rebuild deletes the manifest entirely before running."""
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"raw": {}, "snippets": {"x.md": {"classified": true}}, "wiki": {}}\n',
        encoding="utf-8",
    )

    # Build a workspace with no raw inputs so all stages are no-op
    (tmp_path / "sample_raw").mkdir()
    (tmp_path / "snippets").mkdir()
    (tmp_path / "classified").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "categories.yaml").write_text(
        "categories: []\n", encoding="utf-8"
    )
    (tmp_path / "config" / "pipeline.yaml").write_text(
        "stages:\n  ingest: {provider: fake, model: x, max_tokens: 1}\n"
        "  classify: {provider: fake, model: x, max_tokens: 1}\n"
        "  consolidate: {provider: fake, model: x, max_tokens: 1}\n"
        "  compile: {provider: fake, model: x, max_tokens: 1}\n",
        encoding="utf-8",
    )

    from pipeline.main import main

    main(["--all", "--rebuild", "--root", str(tmp_path)])

    # Manifest should be empty (or only have stage state from this run)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["snippets"] == {}


def test_rebuild_classify_stage_clears_classified_flags(tmp_path: Path) -> None:
    """--stage classify --rebuild flips all snippets[].classified to false but
    preserves other manifest data."""
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({
            "raw": {"r.md": {"content_hash": "h"}},
            "snippets": {
                "snippets/a.md": {"source_hash": "h1", "classified": True, "classified_path": ["x"]},
                "snippets/b.md": {"source_hash": "h2", "classified": True, "classified_path": ["y"]},
            },
            "wiki": {"wiki/01-principles/x.md": {"cluster_fingerprint": "f"}},
            "consolidate": {"01-principles": {"path_frequency_hash": "h"}},
            "known_paths_cache": {"01-principles": [["x"], ["y"]]},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    # No snippets to classify -> stage no-op, but manifest fields cleared
    (tmp_path / "snippets").mkdir()
    (tmp_path / "classified").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "categories.yaml").write_text(
        "categories: []\n", encoding="utf-8"
    )
    (tmp_path / "config" / "pipeline.yaml").write_text(
        "stages:\n  classify: {provider: fake, model: x, max_tokens: 1}\n",
        encoding="utf-8",
    )

    from pipeline.main import main

    main(["--stage", "classify", "--rebuild", "--root", str(tmp_path)])

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    # classified flags reset
    assert data["snippets"]["snippets/a.md"]["classified"] is False
    assert "classified_path" not in data["snippets"]["snippets/a.md"]
    # known_paths_cache cleared (will be rebuilt by classify run)
    assert data["known_paths_cache"] == {}
    # wiki and consolidate untouched
    assert data["wiki"]["wiki/01-principles/x.md"]["cluster_fingerprint"] == "f"
    assert data["consolidate"]["01-principles"]["path_frequency_hash"] == "h"


def test_rebuild_consolidate_clears_consolidate_only(tmp_path: Path) -> None:
    """--stage consolidate --rebuild clears just manifest.consolidate."""
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({
            "raw": {},
            "snippets": {"snippets/a.md": {"source_hash": "h", "classified": True}},
            "wiki": {},
            "consolidate": {"01-principles": {"path_frequency_hash": "h"}},
            "known_paths_cache": {"01-principles": [["x"]]},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    (tmp_path / "classified").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "categories.yaml").write_text("categories: []\n", encoding="utf-8")
    (tmp_path / "config" / "pipeline.yaml").write_text(
        "stages:\n  consolidate: {provider: fake, model: x, max_tokens: 1}\n",
        encoding="utf-8",
    )

    from pipeline.main import main

    main(["--stage", "consolidate", "--rebuild", "--root", str(tmp_path)])

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["consolidate"] == {}
    # Other fields preserved
    assert data["snippets"]["snippets/a.md"]["classified"] is True


def test_rebuild_compile_clears_wiki_fingerprints(tmp_path: Path) -> None:
    """--stage compile --rebuild clears wiki entries."""
    manifest_path = tmp_path / "state" / "ingest_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({
            "raw": {},
            "snippets": {},
            "wiki": {"wiki/01-principles/x.md": {"cluster_fingerprint": "f"}},
            "consolidate": {},
            "known_paths_cache": {},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    (tmp_path / "classified").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "state" / "clusters.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "categories.yaml").write_text("categories: []\n", encoding="utf-8")
    (tmp_path / "config" / "pipeline.yaml").write_text(
        "stages:\n  compile: {provider: fake, model: x, max_tokens: 1}\n",
        encoding="utf-8",
    )

    from pipeline.main import main

    main(["--stage", "compile", "--rebuild", "--root", str(tmp_path)])

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["wiki"] == {}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_main_cli.py -v -k rebuild`
Expected: FAIL — `--rebuild` flag not parsed.

- [ ] **Step 3: Update `pipeline/main.py`**

```python
from __future__ import annotations

import argparse
import json
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
        # cluster, index, diff: nothing to clear (full rebuild every time)
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_main_cli.py -v`
Expected: PASS — all CLI tests including new `--rebuild` tests.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/main.py tests/test_main_cli.py
git commit -m "feat: add --rebuild flag for forcing stage re-execution

--all --rebuild deletes the manifest entirely.
--stage X --rebuild clears only the fields stage X treats as cached:
  classify -> snippets[].classified, known_paths_cache
  consolidate -> consolidate
  compile -> wiki
  ingest -> raw"
```

---

## Phase 4: Splatoon 多層化

### Task 13: 既存データの移行（フェーズ 1）

**Files:**
- Run: `scripts/migrate_to_path.py`

- [ ] **Step 1: Run migration on actual workspace**

```bash
uv run python -m scripts.migrate_to_path
```

Expected: classified/*/*.md と wiki/*/*.md の frontmatter が `subtopic` から `path` に書き換わる。`state/ingest_manifest.json` に `known_paths_cache` と各 snippet の `classified_path` が追加される。

- [ ] **Step 2: Verify migration**

```bash
# Spot-check a classified file
head -10 classified/01-principles/2026-04-21-dakai-principles-and-routes.md
# Expected: path: ['<old subtopic>'] in frontmatter, no subtopic field

# Verify manifest
uv run python -c "import json; d = json.load(open('state/ingest_manifest.json')); print(list(d['known_paths_cache'].keys())); print(list(d['known_paths_cache']['01-principles'])[:3])"
```

- [ ] **Step 3: Run full pipeline (no rebuild) to confirm idempotence**

```bash
uv run python -m pipeline.main --all
```

Expected: pipeline runs end-to-end. consolidate may invoke LLM on first run after migration (path_frequency_hash empty). compile may rewrite wiki pages with new path frontmatter.

- [ ] **Step 4: Run tests**

```bash
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 5: Commit migrated data**

```bash
git add classified/ wiki/ state/
git commit -m "chore: migrate existing data to path-based frontmatter

Runs scripts/migrate_to_path.py on the Splatoon PoC workspace. All
existing classified/ and wiki/ files now use path: [<subtopic>]
(1-element). Manifest gains known_paths_cache and classified_path."
```

---

### Task 14: Splatoon カテゴリ 02/03 の多層化定義

**Files:**
- Modify: `config/categories.yaml`

- [ ] **Step 1: Determine the canonical taxonomy**

設計時の判断（spec §5.1 例に従う）:
- `02-rule-stage`: 2 層（ルール × ステージ、両方 enumerated、親非依存）
- `03-weapon-role`: 2 層（ブキ種別 × 個別ブキ、両方 enumerated、親依存）

Splatoon 3 のルール集合（5 種）:
- area (ガチエリア), yagura (ガチヤグラ), hoko (ガチホコ), asari (ガチアサリ), nawabari (ナワバリ)

Splatoon 3 のステージ集合（執筆時点で稼働中のもの、必要に応じて追加可）:
- zatou (ザトウマーケット), kinme (キンメダイ美術館), masaba (マサバ海峡大橋),
  yagara (ヤガラ市場), namero (ナメロウ金属), ohyo (オヒョウ海運),
  sumeshi (スメーシーワールド), gonzui (ゴンズイ地区), takaashi (タカアシ経済特区),
  kombu (コンブトラック), shinginza (海女美術大学), bangaitei (バンカラ街),
  hirame (ヒラメが丘団地)
（最低限の集合で開始し、不足分は YAML 編集で追加可能）

ブキ種別:
- shooter, roller, charger, slosher, splatling, dualies, brella, blaster, brush, stringer, splatana

個別ブキ（PoC スコープではブキ種別ごとに代表的な数個ずつ。網羅は YAGNI）:
- shooter: splash-shooter, bold-marker, prime-shooter, splattershot-jr, splash-o-matic, ..52-gal
- roller: splat-roller, dynamo-roller, carbon-roller, flingza-roller
- charger: splat-charger, e-liter-4k, squiffer
- slosher: slosher, tri-slosher, bloblobber
- splatling: splatling, hydra-splatling, mini-splatling
- dualies: dapple-dualies, splat-dualies, dualie-squelchers
- brella: splat-brella, tenta-brella, undercover-brella
- blaster: blaster, range-blaster, rapid-blaster
- brush: inkbrush, octobrush
- stringer: tri-stringer, reef-lux-450
- splatana: splatana-stamper, splatana-wiper

実際の値を決めるのは実装担当の判断で OK だが、spec §14 の「`values_by_parent` の表現が冗長になる」未解決事項に従い、必要に応じて `config/categories/03-weapon-role.yaml` のような分割を検討する（このタスクでは分割しない、単一ファイルで進める）。

- [ ] **Step 2: Update `config/categories.yaml`**

下記を新スキーマで書き換える:

```yaml
categories:
  - id: 01-principles
    label: 原理原則
    description: ルール・ステージ・ブキ非依存の普遍理論
    fixed_levels: []

  - id: 02-rule-stage
    label: ルール×ステージ
    description: ルール×ステージ固有の定石
    fixed_levels:
      - name: ルール
        mode: enumerated
        values:
          - {id: area, label: ガチエリア}
          - {id: yagura, label: ガチヤグラ}
          - {id: hoko, label: ガチホコ}
          - {id: asari, label: ガチアサリ}
          - {id: nawabari, label: ナワバリ}
      - name: ステージ
        mode: enumerated
        values:
          - {id: zatou, label: ザトウマーケット}
          - {id: kinme, label: キンメダイ美術館}
          - {id: masaba, label: マサバ海峡大橋}
          - {id: yagara, label: ヤガラ市場}
          - {id: namero, label: ナメロウ金属}
          - {id: ohyo, label: オヒョウ海運}
          - {id: sumeshi, label: スメーシーワールド}
          - {id: gonzui, label: ゴンズイ地区}
          - {id: takaashi, label: タカアシ経済特区}
          - {id: kombu, label: コンブトラック}
          - {id: shinginza, label: 海女美術大学}
          - {id: bangaitei, label: バンカラ街}
          - {id: hirame, label: ヒラメが丘団地}

  - id: 03-weapon-role
    label: ブキ・役割
    description: ブキ／サブ／スペシャル／ロール固有のノウハウ（ギアパワー構成含む）
    fixed_levels:
      - name: ブキ種別
        mode: enumerated
        values:
          - {id: shooter, label: シューター}
          - {id: roller, label: ローラー}
          - {id: charger, label: チャージャー}
          - {id: slosher, label: スロッシャー}
          - {id: splatling, label: スピナー}
          - {id: dualies, label: マニューバー}
          - {id: brella, label: シェルター}
          - {id: blaster, label: ブラスター}
          - {id: brush, label: フデ}
          - {id: stringer, label: ストリンガー}
          - {id: splatana, label: ワイパー}
      - name: 個別ブキ
        mode: enumerated
        values_by_parent:
          shooter:
            - {id: splash-shooter, label: スプラシューター}
            - {id: bold-marker, label: ボールドマーカー}
            - {id: prime-shooter, label: プライムシューター}
            - {id: splattershot-jr, label: わかばシューター}
            - {id: splash-o-matic, label: シャープマーカー}
            - {id: 52-gal, label: ".52ガロン"}
          roller:
            - {id: splat-roller, label: スプラローラー}
            - {id: dynamo-roller, label: ダイナモローラー}
            - {id: carbon-roller, label: カーボンローラー}
            - {id: flingza-roller, label: ヴァリアブルローラー}
          charger:
            - {id: splat-charger, label: スプラチャージャー}
            - {id: e-liter-4k, label: リッター4K}
            - {id: squiffer, label: スクイックリン}
          slosher:
            - {id: slosher, label: バケットスロッシャー}
            - {id: tri-slosher, label: ヒッセン}
            - {id: bloblobber, label: オーバーフロッシャー}
          splatling:
            - {id: splatling, label: スプラスピナー}
            - {id: hydra-splatling, label: ハイドラント}
            - {id: mini-splatling, label: バレルスピナー}
          dualies:
            - {id: dapple-dualies, label: スパッタリー}
            - {id: splat-dualies, label: スプラマニューバー}
            - {id: dualie-squelchers, label: デュアルスイーパー}
          brella:
            - {id: splat-brella, label: パラシェルター}
            - {id: tenta-brella, label: キャンピングシェルター}
            - {id: undercover-brella, label: スパイガジェット}
          blaster:
            - {id: blaster, label: ホットブラスター}
            - {id: range-blaster, label: ロングブラスター}
            - {id: rapid-blaster, label: ラピッドブラスター}
          brush:
            - {id: inkbrush, label: パブロ}
            - {id: octobrush, label: ホクサイ}
          stringer:
            - {id: tri-stringer, label: トライストリンガー}
            - {id: reef-lux-450, label: フルイドV}
          splatana:
            - {id: splatana-stamper, label: ドライブワイパー}
            - {id: splatana-wiper, label: ジムワイパー}

  - id: 04-stepup
    label: ステップアップガイド
    description: XP1800-2400 向けに ①②③ から抽出したエッセンス集
    fixed_levels: []

  - id: 05-glossary
    label: 用語集
    description: スプラトゥーン用語／FPS・TPS 用語
    fixed_levels: []
```

注: `05-glossary` は「用語カテゴリ」の `mode: open` 層を spec で例示していたが、PoC スコープでは fixed_levels なしで開始する（YAGNI）。将来用語数が増えてカテゴリ分けが必要になったら追加する。

- [ ] **Step 3: Verify config loads correctly**

```bash
uv run python -c "from pipeline.config import load_categories; from pathlib import Path; cats = load_categories(Path('config/categories.yaml')); print([(c.id, len(c.fixed_levels)) for c in cats])"
```

Expected: `[('01-principles', 0), ('02-rule-stage', 2), ('03-weapon-role', 2), ('04-stepup', 0), ('05-glossary', 0)]`

- [ ] **Step 4: Commit**

```bash
git add config/categories.yaml
git commit -m "feat: define 2-layer fixed taxonomy for 02/03 categories

02-rule-stage: ルール × ステージ (parent-agnostic)
03-weapon-role: ブキ種別 × 個別ブキ (parent-dependent)

Both use enumerated mode. Other categories keep fixed_levels: [] for
LLM-driven taxonomy. List of weapons is illustrative — extend YAML as
new weapons appear in PoC content."
```

---

### Task 15: 全データを再分類して多層化を反映

**Files:**
- Run: `pipeline/main.py`

- [ ] **Step 1: Delete the existing wiki/ directory**

多層化で配置が変わるため、古いファイルを除去:

```bash
rm -rf wiki/01-principles wiki/02-rule-stage wiki/03-weapon-role wiki/04-stepup wiki/05-glossary
rm -f wiki/README.md
```

(`wiki/` 自体は残す)

- [ ] **Step 2: Reclassify all snippets with new schema**

```bash
uv run python -m pipeline.main --stage classify --rebuild
```

Expected: 全 snippet が再分類される。02-rule-stage や 03-weapon-role に分類されたスニペットは多層パスを取得する（例: `["shooter", "splash-shooter", "ギア構成"]`）。

- [ ] **Step 3: Run remaining stages**

```bash
uv run python -m pipeline.main --stage cluster
uv run python -m pipeline.main --stage compile
uv run python -m pipeline.main --stage consolidate
uv run python -m pipeline.main --stage index
```

Expected: 多層 wiki ツリーが生成される。中間ノードに README が作られる。

- [ ] **Step 4: Verify output**

```bash
# Check the wiki tree structure
find wiki -type f -name "*.md" | head -20

# Spot-check an intermediate README (if 03-weapon-role/shooter/* exists)
ls wiki/03-weapon-role/ 2>/dev/null && cat wiki/03-weapon-role/README.md
```

Expected: `wiki/03-weapon-role/<ブキ種別>/<個別ブキ>/<topic>.md` のようなネスト構造、各中間階層に README.md。

- [ ] **Step 5: Run tests**

```bash
uv run pytest -v
```

Expected: PASS — 全テスト緑。

- [ ] **Step 6: Commit regenerated wiki**

```bash
git add classified/ wiki/ state/
git commit -m "wiki: regenerate with multi-level path taxonomy

Reclassifies all snippets under the new 02/03 hierarchy. wiki/ tree is
now nested with intermediate README.md files for navigation."
```

---

## Phase 5: TODO 追記

### Task 16: TODO.md に YAGNI 退避項目を追加

**Files:**
- Modify: `TODO.md`

- [ ] **Step 1: Read current TODO.md to find insertion point**

```bash
cat TODO.md
```

- [ ] **Step 2: Append the new section to TODO.md**

ファイル末尾の `## 対処済み（履歴）` セクション直前（あるいは `## Minor` セクション直下）に挿入:

```markdown
## 階層タクソノミー × 差分実行（2026-04-30 spec から退避した将来検討項目）

設計 spec: [docs/superpowers/specs/2026-04-30-hierarchical-taxonomy-and-incremental-execution-design.md](docs/superpowers/specs/2026-04-30-hierarchical-taxonomy-and-incremental-execution-design.md)

### N. 設定変更時の自動再生成（YAGNI、将来検討）

**背景**: 差分実行はデータ変更のみ追従。プロンプト・モデル・categories.yaml の
変更時は `--rebuild` で明示的にやり直す前提（spec §3.3）。

**改善余地（段階的に重い順）**:
1. プロンプト/モデルハッシュを manifest に記録、変わったら自動再生成
2. categories.yaml の enumerated 値追加 → 該当ブランチだけ再 classify
3. AI が更新範囲を判断して必要部分だけ再生成（究極形、超 YAGNI）

**いつ対処するか**: 運用で「設定変えたのに反映されない」事故が頻発したら。

### N+1. 中間ノードの LLM 生成 README（YAGNI）

**背景**: 現状は静的索引（リンク一覧）のみ（spec §3.2 案 C）。LLM が「シューターという
種別の概要」のような説明文を書けば閲覧体験は向上する。ただしノード数だけ LLM コール
が増える。

**いつ対処するか**: ユーザーが中間ノードの説明を欲しがる事象が観測されたら。

### N+2. 並列化 / 非同期化（YAGNI）

**背景**: 差分実行で十分速いはず。観測してから判断する。

**いつ対処するか**: 差分実行下でも実行時間が運用許容を超えるとき。

### N+3. 第 2 テナント（社内ナレッジ）並走（YAGNI）

**背景**: spec §2 で C 案として提示。Splatoon 多層化（B）の見通しが立ってから取り組む。

**いつ対処するか**: B 案の実運用がしばらく回り、汎用化の証明が必要なとき。

### N+4. リーフが中間ノードに昇格するケース（実装時に未解決）

**背景**: 既存リーフ `wiki/X/foo.md` に対して、後から path `[X, foo, bar]` の snippet
が追加されたら `foo` は中間ノードに昇格する。`wiki/X/foo.md` と `wiki/X/foo/`
ディレクトリが衝突（spec §14）。

**想定対応**: compile ステージで衝突検知 → 旧リーフを `wiki/X/foo/_index.md` に退避し、
ディレクトリを作成。index ステージは `_index.md` を「直接配下のページ」として扱う。

**いつ対処するか**: 実運用でこのシナリオが発生したら。E2E テストでカバー。

### N+5. ブキ・ステージ列挙の自動生成（運用負荷）

**背景**: `config/categories.yaml` の `02-rule-stage` のステージ列挙、`03-weapon-role`
の `values_by_parent` のブキ列挙は、新コンテンツ追加で増える可能性。手動メンテは
苦痛になりかねない。

**改善余地**:
- `config/categories/03-weapon-role.yaml` のような分割
- 公式ブキデータ（CSV / JSON）からの自動生成スクリプト

**いつ対処するか**: ブキ追加で YAML が膨れすぎたら。
```

- [ ] **Step 3: Verify**

```bash
grep -A 2 "階層タクソノミー" TODO.md | head -10
```

Expected: 新セクションが追記されている。

- [ ] **Step 4: Commit**

```bash
git add TODO.md
git commit -m "docs: record YAGNI items deferred from path/incremental spec

Adds 6 future-consideration items to TODO.md, all referenced from
the 2026-04-30 design spec. None are urgent; they document decisions
made during brainstorming so they're not forgotten."
```

---

## 完了条件

以下が全て満たされて、本プランは完了:

1. `uv run pytest -v` が緑（全テストパス）
2. `uv run ruff check .` がエラーゼロ
3. `uv run ruff format --check .` がエラーゼロ
4. `uv run python -m pipeline.main --all` が成功（Splatoon の 5 カテゴリで多層化済み wiki が生成される）
5. `wiki/03-weapon-role/シューター/` のような多層ディレクトリと、各中間階層の `README.md` が存在
6. `state/ingest_manifest.json` に `consolidate.<cat>.path_frequency_hash` と `known_paths_cache.<cat>` が記録されている
7. `uv run python -m pipeline.main --stage consolidate` の 2 回目実行で LLM コールがゼロ（カテゴリ単位スキップ動作）
8. spec の §11 段階的実装の全 7 ブロックが実装済み

---

## 既知の注意事項（実装担当へ）

- **Phase 2 は 1 つの feature branch（例: `feat/path-taxonomy`）で進めること**。Task 4 のモデル変更コミット直後はステージ側がコンパイルエラーになるが、Task 11 までで全テスト緑に戻す。
- Phase 4 Task 15 の再分類は LLM コストが発生する。Splatoon の現状 snippet 数（~21 件）であれば許容範囲。
- categories.yaml の値リスト（特に `values_by_parent`）の網羅性は PoC スコープでは要求しない。LLM が出力する「未知のブキ id」が分類エラーになるが、その時点で YAML を追記するで運用可能。
- consolidate ステージの `manifest_path` 引数追加に伴う pipeline/main.py の変更は Task 9 内に含めた。Task 12 のみで pipeline/main.py を再編する場合は重複に注意。
