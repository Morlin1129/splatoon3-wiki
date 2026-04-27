# Wiki Knowledge Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the wiki pipeline from producing date-stamped per-snippet pages. Add a consolidate stage that uses an LLM to merge similar/redundant subtopics into stable knowledge pages, while leaving tombstone files behind so existing URLs survive.

**Architecture:**
- Fix the existing `classify` stage's `known_subtopics` bug (it currently feeds file stems instead of frontmatter `subtopic` values) and tighten its prompt to discourage date-prefixed slugs.
- Insert a new `consolidate` stage between `classify` and `cluster`. It calls the LLM per category with the current subtopic list, expects conservative judgement (LLM is instructed to prefer "no change"), applies any returned renames by rewriting classified frontmatter, and replaces the old wiki page with a tombstone that links to the merge target.
- Extend `WikiFrontmatter` with `tombstone`, `merged_into`, `merged_at` so tombstones are machine-distinguishable from live pages. Update `index` to skip tombstones.

**Tech Stack:** Python 3.12, pydantic, pytest, ruff, uv

**Spec:** [docs/superpowers/specs/2026-04-26-wiki-knowledge-consolidation-design.md](../specs/2026-04-26-wiki-knowledge-consolidation-design.md)

---

## File Structure

### New files

- `pipeline/stages/consolidate.py` — consolidate stage entry point + helpers
- `pipeline/prompts/consolidate.md` — system prompt for consolidate stage
- `tests/stages/test_consolidate.py` — unit tests for consolidate stage

### Modified files

- `pipeline/models.py` — add tombstone fields to `WikiFrontmatter`
- `pipeline/stages/classify.py` — fix `known_subtopics` to read frontmatter
- `pipeline/stages/index.py` — skip tombstone pages from page list and counts
- `pipeline/prompts/classify.md` — add naming rules (no dates, prefer reuse)
- `pipeline/main.py` — register `consolidate` in `STAGE_NAMES` and `_run_stage`
- `config/pipeline.yaml` — add `stages.consolidate` config block
- `tests/test_models.py` — add tests for new tombstone fields
- `tests/stages/test_classify.py` — assert frontmatter values are passed in user prompt
- `tests/stages/test_index.py` — add tombstone-exclusion tests
- `tests/test_main_cli.py` — accept `--stage consolidate`
- `tests/test_end_to_end.py` — add consolidate step (no-op rename) to E2E flow

### Untouched (intentionally)

- `pipeline/stages/cluster.py`, `pipeline/stages/compile.py` — automatically benefit from consolidate's frontmatter rewrites; no code change needed
- `pipeline/state.py`, `pipeline/frontmatter_io.py` — reused as-is
- snippet/classified file naming — unchanged (date-prefix stays as ingest-derived ID)

---

## Tasks

### Task 1: Extend `WikiFrontmatter` with tombstone fields

**Files:**
- Modify: `pipeline/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for the new fields**

Append to `tests/test_models.py`:

```python
def test_wiki_frontmatter_tombstone_defaults_off() -> None:
    fm = WikiFrontmatter(
        title="海女美術 ガチエリア定石",
        category="02-rule-stage",
        subtopic="amabi-area-fundamentals",
        sources=[],
        updated_at=datetime(2026, 4, 24, 12, 0, 0),
    )
    assert fm.tombstone is False
    assert fm.merged_into is None
    assert fm.merged_at is None


def test_wiki_frontmatter_tombstone_carries_merge_metadata() -> None:
    merged_at = datetime(2026, 4, 26, 14, 32, 0)
    fm = WikiFrontmatter(
        title="統合済み: 2026-04-26-general-dakai-home-base-clearing",
        category="01-principles",
        subtopic="2026-04-26-general-dakai-home-base-clearing",
        sources=[],
        updated_at=merged_at,
        tombstone=True,
        merged_into="dakai-fundamentals",
        merged_at=merged_at,
    )
    assert fm.tombstone is True
    assert fm.merged_into == "dakai-fundamentals"
    assert fm.merged_at == merged_at
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_models.py::test_wiki_frontmatter_tombstone_defaults_off tests/test_models.py::test_wiki_frontmatter_tombstone_carries_merge_metadata -v`

Expected: FAIL with `pydantic_core._pydantic_core.ValidationError` about extra inputs / unknown fields, or `AttributeError: ... has no attribute 'tombstone'`.

- [ ] **Step 3: Add the new fields to `WikiFrontmatter`**

Replace the `WikiFrontmatter` class in `pipeline/models.py`:

```python
class WikiFrontmatter(BaseModel):
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subtopic: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    updated_at: datetime
    tombstone: bool = False
    merged_into: str | None = None
    merged_at: datetime | None = None
```

- [ ] **Step 4: Run all model tests**

Run: `uv run pytest tests/test_models.py -v`

Expected: all tests pass (including the 2 new ones).

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `uv run pytest`

Expected: all tests pass. (Existing wiki pages without `tombstone` field load fine because the default is `False`.)

- [ ] **Step 6: Commit**

```bash
git add pipeline/models.py tests/test_models.py
git commit -m "feat(models): add tombstone fields to WikiFrontmatter"
```

---

### Task 2: Fix `classify` to feed frontmatter subtopics (not file stems) to LLM

**Files:**
- Modify: `pipeline/stages/classify.py:46-48`
- Test: `tests/stages/test_classify.py`

**Background:** Current code uses `p.stem for ... p in cat_dir.glob("*.md")`. The stem is the snippet filename (date-prefixed), not the actual subtopic value. This causes the LLM to model new subtopics on the date-prefixed pattern.

- [ ] **Step 1: Add a failing test asserting frontmatter values appear in the user prompt**

Append to `tests/stages/test_classify.py`:

```python
def test_classify_passes_existing_frontmatter_subtopics_to_prompt(workspace: Path) -> None:
    # Pre-existing classified file with a clean (non-dated) subtopic in frontmatter
    classified_dir = workspace / "classified" / "01-principles"
    classified_dir.mkdir(parents=True)
    existing_fm = ClassifiedFrontmatter(
        source_file="sample_raw/old.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="hold",
        category="01-principles",
        subtopic="dakai-fundamentals",
    )
    write_frontmatter(
        classified_dir / "2026-04-01-old-snippet.md",
        existing_fm,
        "古いスニペット本文",
    )

    snippet_path = _seed_snippet(workspace, "2026-04-26-new.md", "新しいスニペット本文")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest(
        snippets={
            str(snippet_path.relative_to(workspace)): {
                "source_hash": "h1",
                "classified": False,
            }
        },
    ).save(manifest_path)

    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "01-principles", "subtopic": "dakai-fundamentals"})]
    )
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="原理原則", description="...")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        system_prompt="CLASSIFY PROMPT",
        root=workspace,
    )

    assert len(provider.calls) == 1
    user_prompt = provider.calls[0].user
    # The clean frontmatter subtopic must be visible to the LLM
    assert "dakai-fundamentals" in user_prompt
    # The dated file stem must NOT appear (that was the bug)
    assert "2026-04-01-old-snippet" not in user_prompt
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `uv run pytest tests/stages/test_classify.py::test_classify_passes_existing_frontmatter_subtopics_to_prompt -v`

Expected: FAIL — assertion `"dakai-fundamentals" in user_prompt` fails (current code feeds `"2026-04-01-old-snippet"` instead) AND `"2026-04-01-old-snippet" not in user_prompt` fails.

- [ ] **Step 3: Replace the `known_subtopics` collection in `pipeline/stages/classify.py`**

Find this block (around line 46-48):

```python
    known_subtopics = [
        p.stem for cat_dir in classified_dir.glob("*/") for p in cat_dir.glob("*.md")
    ]
```

Replace with:

```python
    known_subtopics: list[str] = []
    for cat_dir in classified_dir.glob("*/"):
        for path in cat_dir.glob("*.md"):
            existing_fm, _ = read_frontmatter(path, ClassifiedFrontmatter)
            if existing_fm is not None:
                known_subtopics.append(existing_fm.subtopic)
```

- [ ] **Step 4: Run the new test plus existing classify tests**

Run: `uv run pytest tests/stages/test_classify.py -v`

Expected: all classify tests pass, including the new one.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/classify.py tests/stages/test_classify.py
git commit -m "fix(classify): feed frontmatter subtopics (not file stems) to LLM"
```

---

### Task 3: Strengthen the classify prompt with subtopic naming rules

**Files:**
- Modify: `pipeline/prompts/classify.md`

**Note:** This task adds prompt text only. No new test (prompts are exercised end-to-end via fake providers; behavior tests live elsewhere). Existing classify tests must still pass.

- [ ] **Step 1: Append naming rules to `pipeline/prompts/classify.md`**

Read the current file. After the existing "ルール:" bullet list, append:

```markdown

## サブトピック命名のルール（重要）

- subtopic は「**普遍的で長期的に成長しうる知識単位**」を表す名前にする
- **日付・個別事象・session 情報を slug に含めない**
  - ❌ `2026-04-26-general-dakai-home-base-clearing`
  - ✅ `dakai-fundamentals`
- 既存の subtopic に類似する内容なら、**必ず既存を再利用する**
- 既存に類似がなく、明らかに新規概念の場合のみ新規生成する
- 迷ったら、最も近い既存 subtopic を選ぶ
```

- [ ] **Step 2: Run the full suite to confirm no regression**

Run: `uv run pytest`

Expected: all tests pass (the prompt is fed to the fake provider as-is; no test asserts its content).

- [ ] **Step 3: Commit**

```bash
git add pipeline/prompts/classify.md
git commit -m "feat(classify): tighten prompt to discourage date-stamped subtopics"
```

---

### Task 4: Create the consolidate prompt file

**Files:**
- Create: `pipeline/prompts/consolidate.md`

- [ ] **Step 1: Write the prompt file**

Create `pipeline/prompts/consolidate.md` with:

```markdown
あなたは Wiki の subtopic 一覧を見て、統合や改名が必要かを判断する。

入力:
- カテゴリ ID
- 現在の subtopic 一覧（各 subtopic に属する snippet 数つき）

タスク: 統合や改名すべき subtopic を判定し、rename map を返す。

## 統合・改名が望ましい強い基準

- 明らかに同じ概念を別名で呼んでいる
  （例: "dakai-fundamentals" と "dakai-principles"）
- 一方が他方の完全な部分集合で、独立した粒度を持たない
- 日付や個別事象を含む slug が、既存の汎用 slug に明確に該当する
  （例: "2026-04-26-general-dakai-home-base-clearing" が
        "dakai-fundamentals" の範疇）

## 統合してはいけない弱い基準

- 「似ている気がする」程度の主観的判断
- 概念の重複が部分的にしかない
- 統合先の wiki ページが大きくなりすぎる懸念がある
- 判断に迷う

迷ったら「変更なし」を選ぶ。Wiki の安定性は変更の活発さより重要。

## 出力形式

JSON のみ、以下の形式で返す。

```json
{"renames": [
  {
    "category": "<category-id>",
    "from": "<old-subtopic>",
    "to": "<new-subtopic>",
    "reason": "<1 文で統合理由>"
  }
]}
```

統合・改名が不要な場合は `{"renames": []}` を返す。

解説や前置き、コードフェンスは出力に含めない。
```

- [ ] **Step 2: Sanity check that `build_system_prompt` can load it**

Run: `uv run python -c "from pathlib import Path; from pipeline.config import build_system_prompt; print(build_system_prompt(Path.cwd(), 'consolidate')[:60])"`

Expected: prints the first 60 chars without error (something like `あなたは Wiki の subtopic 一覧を見て、統合や改名が必要かを判断する。`).

- [ ] **Step 3: Commit**

```bash
git add pipeline/prompts/consolidate.md
git commit -m "feat(prompts): add consolidate stage system prompt"
```

---

### Task 5: Implement consolidate stage skeleton — handle empty renames

**Files:**
- Create: `pipeline/stages/consolidate.py`
- Modify: `pipeline/stages/__init__.py` (no code change needed if it's empty; otherwise re-export per existing convention)
- Test: `tests/stages/test_consolidate.py`

**Goal of this task:** Get the stage callable end-to-end with a `{"renames": []}` LLM response producing zero side effects. Rename application logic comes in Task 6.

- [ ] **Step 1: Write the failing test for empty renames**

Create `tests/stages/test_consolidate.py`:

```python
import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.stages import consolidate


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "classified").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "state").mkdir()
    return tmp_path


def _seed_classified(
    workspace: Path, category: str, name: str, subtopic: str, body: str = "本文"
) -> Path:
    path = workspace / "classified" / category / name
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
        category=category,
        subtopic=subtopic,
    )
    write_frontmatter(path, fm, body)
    return path


def test_consolidate_no_op_when_no_classified_files(workspace: Path) -> None:
    provider = FakeLLMProvider(responses=[])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )
    assert provider.calls == []
    assert not (workspace / "state" / "consolidate_log.md").exists()


def test_consolidate_no_changes_when_llm_returns_empty_renames(workspace: Path) -> None:
    classified_path = _seed_classified(
        workspace, "01-principles", "2026-04-26-x.md", "dakai-fundamentals"
    )
    original = classified_path.read_text(encoding="utf-8")

    provider = FakeLLMProvider(responses=[json.dumps({"renames": []})])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    assert len(provider.calls) == 1
    # category id and subtopic must be in the user prompt
    assert "01-principles" in provider.calls[0].user
    assert "dakai-fundamentals" in provider.calls[0].user
    # No file changes
    assert classified_path.read_text(encoding="utf-8") == original
    assert not (workspace / "state" / "consolidate_log.md").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/stages/test_consolidate.py -v`

Expected: FAIL with `ImportError` / `ModuleNotFoundError: pipeline.stages.consolidate`.

- [ ] **Step 3: Create the consolidate stage with the minimal logic**

Create `pipeline/stages/consolidate.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import StageConfig
from pipeline.frontmatter_io import read_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _collect_subtopics(classified_dir: Path) -> dict[str, dict[str, int]]:
    """Return {category_id: {subtopic: snippet_count}} for non-empty categories."""
    by_cat: dict[str, dict[str, int]] = {}
    for cat_dir in sorted(classified_dir.glob("*/")):
        cat_id = cat_dir.name
        counts: dict[str, int] = {}
        for path in sorted(cat_dir.glob("*.md")):
            fm, _ = read_frontmatter(path, ClassifiedFrontmatter)
            if fm is None:
                raise RuntimeError(f"unreachable: classified missing frontmatter: {path}")
            counts[fm.subtopic] = counts.get(fm.subtopic, 0) + 1
        if counts:
            by_cat[cat_id] = counts
    return by_cat


def _build_user_prompt(category_id: str, subtopics: dict[str, int]) -> str:
    lines = [f"カテゴリ: {category_id}", "", "現在の subtopic 一覧 (snippet 数):"]
    for subtopic, count in sorted(subtopics.items()):
        lines.append(f"- {subtopic}: {count}")
    return "\n".join(lines)


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    classified_dir: Path,
    wiki_dir: Path,
    log_path: Path,
    system_prompt: str,
    now: Callable[[], datetime] = _now_utc,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    debug_dir = root / "state" / "debug"

    by_cat = _collect_subtopics(classified_dir)
    if not by_cat:
        return

    for cat_id, subtopics in by_cat.items():
        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(cat_id, subtopics),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="consolidate", debug_dir=debug_dir)
        renames = parsed.get("renames", [])
        if renames:
            # Renaming is implemented in a later task; for now this branch is
            # intentionally unreachable in tests (Task 5 only covers the empty-
            # renames path). Task 6 replaces this with real apply logic.
            raise NotImplementedError("consolidate rename application not yet implemented")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/stages/test_consolidate.py -v`

Expected: both tests pass.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/consolidate.py tests/stages/test_consolidate.py
git commit -m "feat(consolidate): add stage skeleton handling empty renames"
```

---

### Task 6: Apply renames — rewrite classified frontmatter, tombstone old wiki, append log

**Files:**
- Modify: `pipeline/stages/consolidate.py`
- Test: `tests/stages/test_consolidate.py`

- [ ] **Step 1: Add failing tests for the rename application**

Append to `tests/stages/test_consolidate.py`:

```python
def test_consolidate_rewrites_classified_frontmatter_to_new_subtopic(
    workspace: Path,
) -> None:
    cls_path = _seed_classified(
        workspace,
        "01-principles",
        "2026-04-26-dakai-home.md",
        "2026-04-26-general-dakai-home-base-clearing",
    )

    rename = {
        "category": "01-principles",
        "from": "2026-04-26-general-dakai-home-base-clearing",
        "to": "dakai-fundamentals",
        "reason": "打開時の自陣処理は dakai-fundamentals の範疇",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    fm, _ = read_frontmatter(cls_path, ClassifiedFrontmatter)
    assert fm.subtopic == "dakai-fundamentals"


def test_consolidate_tombstones_old_wiki_page(workspace: Path) -> None:
    _seed_classified(
        workspace,
        "01-principles",
        "2026-04-26-dakai-home.md",
        "2026-04-26-general-dakai-home-base-clearing",
    )
    # Pre-existing wiki page from a prior compile run
    wiki_dir = workspace / "wiki" / "01-principles"
    wiki_dir.mkdir(parents=True)
    old_wiki = wiki_dir / "2026-04-26-general-dakai-home-base-clearing.md"
    old_fm = WikiFrontmatter(
        title="2026-04-26-general-dakai-home-base-clearing",
        category="01-principles",
        subtopic="2026-04-26-general-dakai-home-base-clearing",
        sources=[],
        updated_at=datetime(2026, 4, 26, 12, 0, 0),
    )
    write_frontmatter(old_wiki, old_fm, "## old\n\n古い本文。\n")

    rename = {
        "category": "01-principles",
        "from": "2026-04-26-general-dakai-home-base-clearing",
        "to": "dakai-fundamentals",
        "reason": "打開時の自陣処理は dakai-fundamentals の範疇",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])
    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    assert old_wiki.exists()  # tombstone file still occupies the URL
    fm, body = read_frontmatter(old_wiki, WikiFrontmatter)
    assert fm.tombstone is True
    assert fm.merged_into == "dakai-fundamentals"
    assert fm.merged_at == datetime(2026, 4, 26, 14, 32, 0)
    assert "[dakai-fundamentals](dakai-fundamentals.md)" in body
    assert "打開時の自陣処理は dakai-fundamentals の範疇" in body
    assert "古い本文" not in body  # old content gone


def test_consolidate_skips_tombstone_when_old_wiki_does_not_exist(
    workspace: Path,
) -> None:
    """If the old subtopic was never compiled to wiki yet, no tombstone needed."""
    _seed_classified(
        workspace,
        "01-principles",
        "2026-04-26-dakai-home.md",
        "2026-04-26-general-dakai-home-base-clearing",
    )
    rename = {
        "category": "01-principles",
        "from": "2026-04-26-general-dakai-home-base-clearing",
        "to": "dakai-fundamentals",
        "reason": "範疇内",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])

    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=workspace / "state" / "consolidate_log.md",
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    # No wiki page existed, so no tombstone created. classified subtopic still updated.
    assert not (workspace / "wiki" / "01-principles" / "2026-04-26-general-dakai-home-base-clearing.md").exists()


def test_consolidate_appends_log_entry(workspace: Path) -> None:
    _seed_classified(
        workspace,
        "01-principles",
        "2026-04-26-x.md",
        "2026-04-26-general-x",
    )
    rename = {
        "category": "01-principles",
        "from": "2026-04-26-general-x",
        "to": "x-fundamentals",
        "reason": "汎用 slug に統合",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])
    log_path = workspace / "state" / "consolidate_log.md"

    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=log_path,
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    text = log_path.read_text(encoding="utf-8")
    assert "2026-04-26T14:32:00" in text
    assert "01-principles/2026-04-26-general-x" in text
    assert "01-principles/x-fundamentals" in text
    assert "汎用 slug に統合" in text


def test_consolidate_log_appends_across_runs(workspace: Path) -> None:
    log_path = workspace / "state" / "consolidate_log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("## existing previous entry\n\nfoo\n", encoding="utf-8")

    _seed_classified(workspace, "01-principles", "2026-04-26-y.md", "old-y")
    rename = {
        "category": "01-principles",
        "from": "old-y",
        "to": "new-y",
        "reason": "test",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])

    consolidate.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        log_path=log_path,
        system_prompt="CONSOLIDATE PROMPT",
        now=lambda: datetime(2026, 4, 26, 14, 32, 0),
        root=workspace,
    )

    text = log_path.read_text(encoding="utf-8")
    assert "## existing previous entry" in text  # preserved
    assert "old-y" in text  # new entry appended
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/stages/test_consolidate.py -v`

Expected: the 4 new tests fail (NotImplementedError raised by Task 5's stub).

- [ ] **Step 3: Replace the `NotImplementedError` branch with real apply logic**

Edit `pipeline/stages/consolidate.py`. Add the imports and helpers, then update `run()`. Replace the existing file with:

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.config import StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.llm.parsing import parse_json_response
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _collect_subtopics(classified_dir: Path) -> dict[str, dict[str, int]]:
    """Return {category_id: {subtopic: snippet_count}} for non-empty categories."""
    by_cat: dict[str, dict[str, int]] = {}
    for cat_dir in sorted(classified_dir.glob("*/")):
        cat_id = cat_dir.name
        counts: dict[str, int] = {}
        for path in sorted(cat_dir.glob("*.md")):
            fm, _ = read_frontmatter(path, ClassifiedFrontmatter)
            if fm is None:
                raise RuntimeError(f"unreachable: classified missing frontmatter: {path}")
            counts[fm.subtopic] = counts.get(fm.subtopic, 0) + 1
        if counts:
            by_cat[cat_id] = counts
    return by_cat


def _build_user_prompt(category_id: str, subtopics: dict[str, int]) -> str:
    lines = [f"カテゴリ: {category_id}", "", "現在の subtopic 一覧 (snippet 数):"]
    for subtopic, count in sorted(subtopics.items()):
        lines.append(f"- {subtopic}: {count}")
    return "\n".join(lines)


def _rewrite_classified_subtopic(
    classified_dir: Path, category: str, src: str, dst: str
) -> None:
    cat_dir = classified_dir / category
    for path in sorted(cat_dir.glob("*.md")):
        fm, body = read_frontmatter(path, ClassifiedFrontmatter)
        if fm is None or fm.subtopic != src:
            continue
        new_fm = ClassifiedFrontmatter(**{**fm.model_dump(), "subtopic": dst})
        write_frontmatter(path, new_fm, body)


def _tombstone_wiki_page(
    wiki_dir: Path, category: str, src: str, dst: str, reason: str, now: datetime
) -> None:
    old_wiki = wiki_dir / category / f"{src}.md"
    if not old_wiki.exists():
        return  # nothing was ever compiled for this subtopic; no URL to preserve
    tombstone_fm = WikiFrontmatter(
        title=f"統合済み: {src}",
        category=category,
        subtopic=src,
        sources=[],
        updated_at=now,
        tombstone=True,
        merged_into=dst,
        merged_at=now,
    )
    body_lines = [
        f"# 統合済み: {src}",
        "",
        f"このページは [{dst}]({dst}.md) に統合されました。",
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
        f"{len(renames)} 件の subtopic を統合した。",
        "",
    ]
    for r in renames:
        cat, src, dst = r["category"], r["from"], r["to"]
        lines.append(f"- `{cat}/{src}` → `{cat}/{dst}`")
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
    classified_dir: Path,
    wiki_dir: Path,
    log_path: Path,
    system_prompt: str,
    now: Callable[[], datetime] = _now_utc,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    debug_dir = root / "state" / "debug"

    by_cat = _collect_subtopics(classified_dir)
    if not by_cat:
        return

    all_renames: list[dict[str, Any]] = []
    for cat_id, subtopics in by_cat.items():
        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(cat_id, subtopics),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = parse_json_response(reply, stage="consolidate", debug_dir=debug_dir)
        all_renames.extend(parsed.get("renames", []))

    if not all_renames:
        return

    ts = now()
    for r in all_renames:
        cat = r["category"]
        src = r["from"]
        dst = r["to"]
        reason = r.get("reason", "")
        _rewrite_classified_subtopic(classified_dir, cat, src, dst)
        _tombstone_wiki_page(wiki_dir, cat, src, dst, reason, ts)
    _append_log(log_path, all_renames, ts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/stages/test_consolidate.py -v`

Expected: all 6 tests pass.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/consolidate.py tests/stages/test_consolidate.py
git commit -m "feat(consolidate): apply renames, tombstone old wiki pages, append log"
```

---

### Task 7: Validate LLM rename output — reject unknown category or unknown source subtopic

**Files:**
- Modify: `pipeline/stages/consolidate.py`
- Test: `tests/stages/test_consolidate.py`

- [ ] **Step 1: Add failing tests for validation**

Append to `tests/stages/test_consolidate.py`:

```python
def test_consolidate_raises_on_unknown_category(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "2026-04-26-x.md", "x-topic")
    rename = {
        "category": "99-bogus",
        "from": "x-topic",
        "to": "y-topic",
        "reason": "test",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])

    with pytest.raises(ValueError, match="unknown category"):
        consolidate.run(
            provider=provider,
            stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
            classified_dir=workspace / "classified",
            wiki_dir=workspace / "wiki",
            log_path=workspace / "state" / "consolidate_log.md",
            system_prompt="CONSOLIDATE PROMPT",
            now=lambda: datetime(2026, 4, 26, 14, 32, 0),
            root=workspace,
        )


def test_consolidate_raises_on_unknown_source_subtopic(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "2026-04-26-x.md", "x-topic")
    rename = {
        "category": "01-principles",
        "from": "does-not-exist",
        "to": "y-topic",
        "reason": "test",
    }
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])

    with pytest.raises(ValueError, match="unknown source subtopic"):
        consolidate.run(
            provider=provider,
            stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
            classified_dir=workspace / "classified",
            wiki_dir=workspace / "wiki",
            log_path=workspace / "state" / "consolidate_log.md",
            system_prompt="CONSOLIDATE PROMPT",
            now=lambda: datetime(2026, 4, 26, 14, 32, 0),
            root=workspace,
        )


def test_consolidate_raises_on_malformed_rename(workspace: Path) -> None:
    _seed_classified(workspace, "01-principles", "2026-04-26-x.md", "x-topic")
    rename = {"category": "01-principles", "from": "x-topic"}  # missing 'to'
    provider = FakeLLMProvider(responses=[json.dumps({"renames": [rename]})])

    with pytest.raises(ValueError, match="malformed rename"):
        consolidate.run(
            provider=provider,
            stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
            classified_dir=workspace / "classified",
            wiki_dir=workspace / "wiki",
            log_path=workspace / "state" / "consolidate_log.md",
            system_prompt="CONSOLIDATE PROMPT",
            now=lambda: datetime(2026, 4, 26, 14, 32, 0),
            root=workspace,
        )
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/stages/test_consolidate.py::test_consolidate_raises_on_unknown_category tests/stages/test_consolidate.py::test_consolidate_raises_on_unknown_source_subtopic tests/stages/test_consolidate.py::test_consolidate_raises_on_malformed_rename -v`

Expected: all 3 fail (no validation in place — `unknown_category` raises `KeyError` from `wiki_dir / category` glob path, `unknown_source_subtopic` silently no-ops, `malformed` raises `KeyError` from missing dict key).

- [ ] **Step 3: Add a `_validate_rename` helper and call it in `run()`**

In `pipeline/stages/consolidate.py`, add this helper above `run()`:

```python
def _validate_rename(rename: dict[str, Any], available: dict[str, dict[str, int]]) -> None:
    cat = rename.get("category")
    src = rename.get("from")
    dst = rename.get("to")
    if not isinstance(cat, str) or not isinstance(src, str) or not isinstance(dst, str):
        raise ValueError(f"consolidate: malformed rename entry: {rename!r}")
    if cat not in available:
        raise ValueError(f"consolidate: unknown category in rename: {cat!r}")
    if src not in available[cat]:
        raise ValueError(f"consolidate: unknown source subtopic in rename: {cat}/{src}")
```

Then in `run()`, after collecting `all_renames` and before applying, validate:

```python
    if not all_renames:
        return

    for r in all_renames:
        _validate_rename(r, by_cat)

    ts = now()
    for r in all_renames:
        # ... existing apply loop unchanged
```

- [ ] **Step 4: Run validation tests to verify they pass**

Run: `uv run pytest tests/stages/test_consolidate.py -v`

Expected: all 9 consolidate tests pass.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/consolidate.py tests/stages/test_consolidate.py
git commit -m "feat(consolidate): validate LLM renames against known categories and subtopics"
```

---

### Task 8: Make `index` stage skip tombstone pages

**Files:**
- Modify: `pipeline/stages/index.py`
- Test: `tests/stages/test_index.py`

- [ ] **Step 1: Add failing tests for tombstone exclusion**

Append to `tests/stages/test_index.py`:

```python
def _write_tombstone_wiki(path: Path, *, subtopic: str, merged_into: str) -> None:
    fm = WikiFrontmatter(
        title=f"統合済み: {subtopic}",
        category=path.parent.name,
        subtopic=subtopic,
        sources=[],
        updated_at=datetime(2026, 4, 26, 14, 32, 0),
        tombstone=True,
        merged_into=merged_into,
        merged_at=datetime(2026, 4, 26, 14, 32, 0),
    )
    body = (
        f"# 統合済み: {subtopic}\n\n"
        f"このページは [{merged_into}]({merged_into}.md) に統合されました。\n"
    )
    write_frontmatter(path, fm, body)


def test_index_excludes_tombstones_from_category_listing(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    cat_dir = wiki_dir / "01-principles"
    cat_dir.mkdir(parents=True)

    _write_wiki(
        cat_dir / "live-page.md",
        title="生きているページ",
        subtopic="live-page",
        body="## 生きているページ\n\n本文。\n",
    )
    _write_tombstone_wiki(
        cat_dir / "old-page.md",
        subtopic="old-page",
        merged_into="live-page",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    cat_readme = (cat_dir / "README.md").read_text(encoding="utf-8")
    assert "[生きているページ](live-page.md)" in cat_readme
    assert "old-page.md" not in cat_readme  # tombstone hidden
    assert "統合済み" not in cat_readme


def test_index_excludes_tombstones_from_top_level_count(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    cat_dir = wiki_dir / "01-principles"
    cat_dir.mkdir(parents=True)

    _write_wiki(
        cat_dir / "live.md",
        title="ライブ",
        subtopic="live",
        body="## ライブ\n\n本文。\n",
    )
    _write_tombstone_wiki(
        cat_dir / "tombstone.md",
        subtopic="tombstone",
        merged_into="live",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    assert "01-principles](01-principles/) — 原理原則 — 1 ページ" in top
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/stages/test_index.py::test_index_excludes_tombstones_from_category_listing tests/stages/test_index.py::test_index_excludes_tombstones_from_top_level_count -v`

Expected: FAIL — both tombstone tests fail because index currently lists every `*.md` file.

- [ ] **Step 3: Filter tombstones in `_list_pages`**

In `pipeline/stages/index.py`, replace `_list_pages`:

```python
def _list_pages(cat_dir: Path) -> list[Path]:
    if not cat_dir.is_dir():
        return []
    pages: list[Path] = []
    for p in sorted(cat_dir.glob("*.md")):
        if p.name == "README.md":
            continue
        fm, _ = read_frontmatter(p, WikiFrontmatter)
        if fm is not None and fm.tombstone:
            continue
        pages.append(p)
    return pages
```

(`_list_pages` is the single source of truth for both per-category listings and top-level page counts via `len(pages)`, so filtering here covers both.)

- [ ] **Step 4: Run index tests to verify they pass**

Run: `uv run pytest tests/stages/test_index.py -v`

Expected: all index tests pass (existing + 2 new).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/index.py tests/stages/test_index.py
git commit -m "feat(index): exclude tombstone wiki pages from listings and counts"
```

---

### Task 9: Wire `consolidate` into `main.py` CLI and `pipeline.yaml`

**Files:**
- Modify: `pipeline/main.py`
- Modify: `config/pipeline.yaml`
- Test: `tests/test_main_cli.py`

- [ ] **Step 1: Add a failing CLI parse test**

Append to `tests/test_main_cli.py`:

```python
def test_parse_args_accepts_consolidate_stage() -> None:
    args = main.parse_args(["--stage", "consolidate"])
    assert args.stage == "consolidate"


def test_stage_names_order_runs_consolidate_between_classify_and_cluster() -> None:
    names = main.STAGE_NAMES
    assert names.index("consolidate") == names.index("classify") + 1
    assert names.index("cluster") == names.index("consolidate") + 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_main_cli.py::test_parse_args_accepts_consolidate_stage tests/test_main_cli.py::test_stage_names_order_runs_consolidate_between_classify_and_cluster -v`

Expected: FAIL — first test rejected by argparse `choices`; second fails on `index("consolidate")` raising ValueError.

- [ ] **Step 3: Register `consolidate` in `pipeline/main.py`**

Replace the `STAGE_NAMES` line and the imports + add a branch in `_run_stage`. Edit `pipeline/main.py`:

Change the import line from:

```python
from pipeline.stages import classify, cluster, diff_commit, index, ingest
```

to:

```python
from pipeline.stages import classify, cluster, consolidate, diff_commit, index, ingest
```

Change `STAGE_NAMES`:

```python
STAGE_NAMES = ["ingest", "classify", "consolidate", "cluster", "compile", "index", "diff"]
```

Add this branch in `_run_stage` between the `classify` and `cluster` branches:

```python
    elif name == "consolidate":
        stage_cfg = pipeline_cfg.stages["consolidate"]
        consolidate.run(
            provider=get_provider(stage_cfg),
            stage_cfg=stage_cfg,
            classified_dir=root / "classified",
            wiki_dir=root / "wiki",
            log_path=root / "state" / "consolidate_log.md",
            system_prompt=build_system_prompt(root, "consolidate"),
            root=root,
        )
```

- [ ] **Step 4: Add `consolidate` to `config/pipeline.yaml`**

Edit `config/pipeline.yaml` and add this block (between `classify` and `compile` sections to preserve readable order):

```yaml
  consolidate:
    provider: gemini
    model: gemini-3-flash-preview
    max_tokens: 4096
```

The full file should now look like:

```yaml
stages:
  ingest:
    provider: gemini
    model: gemini-3-flash-preview
    # Japanese prose costs more tokens than English; raise the cap so the
    # model can finish a multi-snippet JSON array without truncation.
    max_tokens: 16384
  classify:
    provider: gemini
    model: gemini-3-flash-preview
    max_tokens: 2048
  consolidate:
    provider: gemini
    model: gemini-3-flash-preview
    max_tokens: 4096
  compile:
    provider: gemini
    model: gemini-3-flash-preview
    max_tokens: 8192
```

- [ ] **Step 5: Run CLI tests + full suite**

Run: `uv run pytest tests/test_main_cli.py -v && uv run pytest`

Expected: CLI tests pass and the rest of the suite stays green.

- [ ] **Step 6: Commit**

```bash
git add pipeline/main.py config/pipeline.yaml tests/test_main_cli.py
git commit -m "feat(cli): register consolidate stage between classify and cluster"
```

---

### Task 10: Add `consolidate` to the end-to-end test

**Files:**
- Modify: `tests/test_end_to_end.py`

- [ ] **Step 1: Add a failing assertion that consolidate runs in the E2E flow**

Edit `tests/test_end_to_end.py`. Add the import alongside other stages:

```python
from pipeline.stages import classify, cluster, consolidate, diff_commit, ingest
```

After the `classify.run(...)` block and before `cluster.run(...)`, insert:

```python
    consolidate_provider = FakeLLMProvider(
        responses=[json.dumps({"renames": []}, ensure_ascii=False)]
    )
    consolidate.run(
        provider=consolidate_provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1024),
        classified_dir=root / "classified",
        wiki_dir=root / "wiki",
        log_path=root / "state" / "consolidate_log.md",
        system_prompt="CONSOLIDATE",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=root,
    )
    # consolidate was called once (one non-empty category) and made no changes
    assert len(consolidate_provider.calls) == 1
    assert not (root / "state" / "consolidate_log.md").exists()
```

- [ ] **Step 2: Run the E2E test to verify it now exercises consolidate**

Run: `uv run pytest tests/test_end_to_end.py -v`

Expected: PASS — consolidate runs, returns empty renames, downstream stages still produce the same wiki page.

- [ ] **Step 3: Run the full suite + lint + format check**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check .`

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py
git commit -m "test(e2e): exercise consolidate stage in the end-to-end flow"
```

---

## Manual Migration (after implementation, not a code task)

Once Task 10 is committed, the consolidate machinery can clean up the existing 7 date-prefixed subtopics in this repo. This is a one-shot operational step, not part of the implementation plan, but listed here so it doesn't get lost.

```bash
# Requires GEMINI_API_KEY in .env
uv run python -m pipeline.main --stage consolidate
# Inspect the new state/consolidate_log.md to see what was merged
# Then re-run cluster + compile + index to refresh wiki pages and READMEs
uv run python -m pipeline.main --stage cluster
uv run python -m pipeline.main --stage compile
uv run python -m pipeline.main --stage index
```

If the LLM produces an unwanted rename, `git checkout classified/ wiki/ state/consolidate_log.md state/clusters.json` reverts it. If the LLM is too conservative and leaves a date-prefixed subtopic in place, edit the relevant `classified/<cat>/*.md` frontmatter `subtopic` field by hand and re-run `cluster → compile → index`.

---

## Acceptance Criteria

- All tasks committed; `git log --oneline` shows ten focused commits.
- `uv run pytest` passes (existing 45-ish tests + the new consolidate, model, classify, index, CLI, and E2E additions).
- `uv run ruff check .` and `uv run ruff format --check .` both clean.
- `uv run python -m pipeline.main --all` runs `ingest → classify → consolidate → cluster → compile → index → diff` in that order.
- A wiki page that gets tombstoned by consolidate retains its original file path (URL stable), has `tombstone: true` in frontmatter, and links to the merge target in its body.
- The index stage's top-level `wiki/README.md` and per-category READMEs do not list tombstones.
