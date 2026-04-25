# Wiki Index Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a code-only `index` stage that generates `wiki/README.md` (category directory) and `wiki/<category>/README.md` (page list with title + 1-line summary), inserted between `compile` and `diff` in the pipeline.

**Architecture:** Single new module `pipeline/stages/index.py` with two helpers (`_extract_title`, `_extract_summary`) and one entrypoint `run(*, wiki_dir, categories)`. The CLI registers it as a stage. No LLM calls, no manifest tracking — full regeneration each run is fast and idempotent.

**Tech Stack:** Python 3.12, pydantic (`WikiFrontmatter`), `pipeline.frontmatter_io.read_frontmatter`, `pipeline.config.Category`. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-24-wiki-index-design.md`

---

## File Structure

**New files:**

- `pipeline/stages/index.py` — title/summary extraction helpers + `run()` that writes README files
- `tests/stages/test_index.py` — pytest tests for helpers and `run()`

**Modified files:**

- `pipeline/main.py` — add `"index"` to `STAGE_NAMES` (between `"compile"` and `"diff"`), add `_run_stage("index", ...)` branch
- `tests/test_main_cli.py` — assert `--stage index` is accepted

**Each file's responsibility:**

- `pipeline/stages/index.py` owns BOTH helpers and the `run()` function. They're tightly coupled; splitting would scatter related logic.
- Tests mirror that split: helper tests + integration tests in one file.

---

## Task 1: Title and summary extraction helpers

**Files:**
- Create: `pipeline/stages/index.py` (with helpers only — `run()` added in Task 2)
- Create: `tests/stages/test_index.py` (helper tests only — integration tests added in Task 2)

- [ ] **Step 1: Write the failing tests for `_extract_title`**

Create `tests/stages/test_index.py`:
```python
from pipeline.stages.index import _extract_summary, _extract_title


def test_extract_title_uses_first_h2() -> None:
    body = "## 海女美術 右高台\n\n本文。\n\n## セクション\n"
    assert _extract_title(body, fallback="slug") == "海女美術 右高台"


def test_extract_title_falls_back_to_h1_when_no_h2() -> None:
    body = "# Top\n\n本文。\n"
    assert _extract_title(body, fallback="slug") == "Top"


def test_extract_title_falls_back_to_slug_when_no_heading() -> None:
    body = "本文だけ。\n"
    assert _extract_title(body, fallback="my-subtopic") == "my-subtopic"


def test_extract_title_strips_trailing_whitespace() -> None:
    body = "##   海女美術  \n"
    assert _extract_title(body, fallback="x") == "海女美術"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/stages/test_index.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.stages.index'`.

- [ ] **Step 3: Implement `_extract_title` in `pipeline/stages/index.py`**

Create `pipeline/stages/index.py`:
```python
from __future__ import annotations


def _extract_title(body: str, *, fallback: str) -> str:
    """Return the first `## ` heading text, else first `# `, else fallback."""
    for prefix in ("## ", "# "):
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(prefix):
                return stripped[len(prefix) :].strip()
    return fallback
```

Note: the tests call `_extract_title(body, fallback="...")` with `fallback` as a positional arg in some places. Update the signature to accept it positionally too if needed. Looking at the tests — they all pass `fallback=...` as keyword. Keep keyword-only (`*, fallback: str`).

- [ ] **Step 4: Run title tests and verify they pass**

Run: `uv run pytest tests/stages/test_index.py::test_extract_title_uses_first_h2 tests/stages/test_index.py::test_extract_title_falls_back_to_h1_when_no_h2 tests/stages/test_index.py::test_extract_title_falls_back_to_slug_when_no_heading tests/stages/test_index.py::test_extract_title_strips_trailing_whitespace -v`
Expected: 4 passed.

- [ ] **Step 5: Add failing tests for `_extract_summary`**

Append to `tests/stages/test_index.py`:
```python
def test_extract_summary_takes_first_sentence_after_title() -> None:
    body = "## タイトル\n\n最初の文。続きの文。\n\n## 別セクション\n"
    assert _extract_summary(body) == "最初の文。"


def test_extract_summary_handles_ascii_period() -> None:
    body = "## Title\n\nFirst sentence. Second sentence.\n"
    assert _extract_summary(body) == "First sentence."


def test_extract_summary_truncates_long_sentence() -> None:
    long_sentence = "あ" * 130 + "。"
    body = f"## タイトル\n\n{long_sentence}\n"
    result = _extract_summary(body)
    assert result.endswith("…")
    # 120 chars of content + the ellipsis
    assert len(result) == 121


def test_extract_summary_returns_placeholder_when_body_empty() -> None:
    body = "## タイトル\n\n"
    assert _extract_summary(body) == "(本文なし)"


def test_extract_summary_skips_bullet_lines() -> None:
    body = "## タイトル\n\n- 箇条書きはサマリにしない\n- 二つ目\n\n通常段落。\n"
    assert _extract_summary(body) == "通常段落。"


def test_extract_summary_works_without_heading() -> None:
    body = "見出しなしの段落。続き。\n"
    assert _extract_summary(body) == "見出しなしの段落。"
```

- [ ] **Step 6: Run summary tests and verify they fail**

Run: `uv run pytest tests/stages/test_index.py -v -k "summary"`
Expected: FAIL with `ImportError` (function not yet defined) or `AttributeError`.

- [ ] **Step 7: Implement `_extract_summary` in `pipeline/stages/index.py`**

Append to `pipeline/stages/index.py`:
```python
_NO_BODY = "(本文なし)"
_PARAGRAPH_BREAK_PREFIXES = ("#", "-", "*", ">", "|", "```")
_SUMMARY_MAX_CHARS = 120


def _extract_summary(body: str) -> str:
    """Return the first sentence of the first non-heading paragraph.

    Falls back to "(本文なし)" if no eligible paragraph is found.
    Sentences end on a Japanese full stop `。` or an ASCII `.` followed by
    whitespace or end-of-string. The result is truncated to 120 Unicode
    code points with "…" appended when the source sentence is longer.
    """
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
```

- [ ] **Step 8: Run all helper tests and verify they pass**

Run: `uv run pytest tests/stages/test_index.py -v`
Expected: 10 passed (4 title + 6 summary).

- [ ] **Step 9: Ruff lint + format**

Run: `uv run ruff check pipeline/stages/index.py tests/stages/test_index.py`
Expected: "All checks passed!"

Run: `uv run ruff format --check pipeline/stages/index.py tests/stages/test_index.py`

If format reports changes, run `uv run ruff format pipeline/stages/index.py tests/stages/test_index.py` and re-verify.

- [ ] **Step 10: Commit**

```bash
git add pipeline/stages/index.py tests/stages/test_index.py
git commit -m "feat(stages): add title and summary extraction helpers for index stage"
```

---

## Task 2: Index stage `run()`

**Files:**
- Modify: `pipeline/stages/index.py` (add imports + `run()`)
- Modify: `tests/stages/test_index.py` (add integration tests)

- [ ] **Step 1: Add the failing integration tests**

Edit `tests/stages/test_index.py`:

(a) Add these new imports to the top of the file, alongside the existing
`from pipeline.stages.index import _extract_summary, _extract_title`:
```python
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category
from pipeline.frontmatter_io import write_frontmatter
from pipeline.models import WikiFrontmatter
from pipeline.stages import index as index_stage
```

(b) Append the following test code at the bottom of the file:
```python


def _write_wiki(path: Path, subtopic: str, body: str) -> None:
    fm = WikiFrontmatter(
        category=path.parent.name,
        subtopic=subtopic,
        sources=[],
        updated_at=datetime(2026, 4, 24, 12, 0, 0),
    )
    write_frontmatter(path, fm, body)


@pytest.fixture
def categories() -> list[Category]:
    return [
        Category(id="01-principles", label="原理原則", description="普遍理論"),
        Category(id="02-rule-stage", label="ルール×ステージ", description="定石"),
        Category(id="03-weapon-role", label="ブキ・役割", description="ブキ別ノウハウ"),
    ]


def test_index_writes_top_level_and_per_category(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "01-principles").mkdir(parents=True)
    (wiki_dir / "02-rule-stage").mkdir(parents=True)
    # 03-weapon-role intentionally absent

    _write_wiki(
        wiki_dir / "01-principles" / "two-down-retreat.md",
        "two-down-retreat",
        "## 2 落ち時の退避\n\n人数不利時はオブジェクト関与より復帰を優先する。\n",
    )
    _write_wiki(
        wiki_dir / "01-principles" / "hate-management.md",
        "hate-management",
        "## ヘイト管理\n\n誰が敵の視線を集めるか役割分担する。\n",
    )
    _write_wiki(
        wiki_dir / "02-rule-stage" / "amabi-right-high.md",
        "amabi-right-high",
        "## 海女美術 右高台\n\n右高台はリスクと裏取り誘発を伴う。\n",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    assert "# Splatoon 3 Wiki" in top
    assert "[01-principles](01-principles/) — 原理原則 — 2 ページ" in top
    assert "[02-rule-stage](02-rule-stage/) — ルール×ステージ — 1 ページ" in top
    assert "[03-weapon-role](03-weapon-role/) — ブキ・役割 — 0 ページ" in top

    cat1 = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")
    assert "# 01-principles — 原理原則" in cat1
    assert "普遍理論" in cat1
    # Pages listed in alphabetical order by filename
    assert cat1.index("hate-management.md") < cat1.index("two-down-retreat.md")
    assert "[ヘイト管理](hate-management.md) — 誰が敵の視線を集めるか役割分担する。" in cat1
    assert (
        "[2 落ち時の退避](two-down-retreat.md) — 人数不利時はオブジェクト関与より復帰を優先する。"
        in cat1
    )

    cat3 = (wiki_dir / "03-weapon-role" / "README.md").read_text(encoding="utf-8")
    assert "(まだページがありません)" in cat3


def test_index_skips_existing_readme_when_counting_and_listing(
    tmp_path: Path, categories: list[Category]
) -> None:
    wiki_dir = tmp_path / "wiki"
    cat_dir = wiki_dir / "01-principles"
    cat_dir.mkdir(parents=True)

    _write_wiki(
        cat_dir / "page-one.md",
        "page-one",
        "## ページ1\n\n本文。\n",
    )
    # Stale README from a previous run
    (cat_dir / "README.md").write_text("# stale", encoding="utf-8")

    index_stage.run(wiki_dir=wiki_dir, categories=categories)

    top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    assert "01-principles](01-principles/) — 原理原則 — 1 ページ" in top  # not 2

    cat1 = (cat_dir / "README.md").read_text(encoding="utf-8")
    assert "page-one" in cat1
    assert "stale" not in cat1


def test_index_is_idempotent(tmp_path: Path, categories: list[Category]) -> None:
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "01-principles").mkdir(parents=True)
    _write_wiki(
        wiki_dir / "01-principles" / "p.md",
        "p",
        "## P\n\n本文。\n",
    )

    index_stage.run(wiki_dir=wiki_dir, categories=categories)
    first_top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    first_cat = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")

    index_stage.run(wiki_dir=wiki_dir, categories=categories)
    second_top = (wiki_dir / "README.md").read_text(encoding="utf-8")
    second_cat = (wiki_dir / "01-principles" / "README.md").read_text(encoding="utf-8")

    assert first_top == second_top
    assert first_cat == second_cat
```

- [ ] **Step 2: Run integration tests and verify they fail**

Run: `uv run pytest tests/stages/test_index.py -v -k "test_index"`
Expected: FAIL with `AttributeError: module 'pipeline.stages.index' has no attribute 'run'` (or similar).

- [ ] **Step 3: Add imports and `run()` to `pipeline/stages/index.py`**

At the top of `pipeline/stages/index.py`, replace the existing imports section with:
```python
from __future__ import annotations

from pathlib import Path

from pipeline.config import Category
from pipeline.frontmatter_io import read_frontmatter
from pipeline.models import WikiFrontmatter
```

At the bottom of the file, append:
```python
def _list_pages(cat_dir: Path) -> list[Path]:
    if not cat_dir.is_dir():
        return []
    return sorted(p for p in cat_dir.glob("*.md") if p.name != "README.md")


def _write_category_readme(
    cat: Category, cat_dir: Path, pages: list[Path]
) -> None:
    lines = [f"# {cat.id} — {cat.label}", "", cat.description, "", "## ページ一覧", ""]
    if not pages:
        lines.append("(まだページがありません)")
    else:
        for page_path in pages:
            fm, body = read_frontmatter(page_path, WikiFrontmatter)
            if fm is None:
                raise RuntimeError(
                    f"unreachable: wiki page missing frontmatter: {page_path}"
                )
            title = _extract_title(body, fallback=fm.subtopic)
            summary = _extract_summary(body)
            lines.append(f"- [{title}]({page_path.name}) — {summary}")
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_top_readme(
    wiki_dir: Path, categories: list[Category], counts: dict[str, int]
) -> None:
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
    """Generate wiki/README.md and per-category README.md files."""
    counts: dict[str, int] = {}
    for cat in categories:
        cat_dir = wiki_dir / cat.id
        pages = _list_pages(cat_dir)
        counts[cat.id] = len(pages)
        _write_category_readme(cat, cat_dir, pages)
    _write_top_readme(wiki_dir, categories, counts)
```

- [ ] **Step 4: Run integration tests and verify they pass**

Run: `uv run pytest tests/stages/test_index.py -v`
Expected: 13 passed (10 helper tests + 3 integration tests).

- [ ] **Step 5: Ruff lint + format**

Run: `uv run ruff check pipeline/stages/index.py tests/stages/test_index.py`
Run: `uv run ruff format --check pipeline/stages/index.py tests/stages/test_index.py`

Auto-fix with `uv run ruff format ...` if needed, then re-verify.

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/index.py tests/stages/test_index.py
git commit -m "feat(stages): add index stage that writes wiki/README.md and per-category READMEs"
```

---

## Task 3: CLI wiring

**Files:**
- Modify: `pipeline/main.py` (add `"index"` to `STAGE_NAMES`, add dispatch branch)
- Modify: `tests/test_main_cli.py` (add stage acceptance test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main_cli.py`:
```python
def test_parse_args_accepts_index_stage() -> None:
    args = main.parse_args(["--stage", "index"])
    assert args.stage == "index"
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_main_cli.py::test_parse_args_accepts_index_stage -v`
Expected: FAIL with `SystemExit` (argparse rejects unknown choice).

- [ ] **Step 3: Modify `pipeline/main.py`**

In `pipeline/main.py`:

(a) Update the `from pipeline.stages import ...` block to include `index`:
```python
from pipeline.stages import classify, cluster, diff_commit, index, ingest
from pipeline.stages import compile as compile_stage
```

(b) Update `STAGE_NAMES`:
```python
STAGE_NAMES = ["ingest", "classify", "cluster", "compile", "index", "diff"]
```

(c) Add a new branch in `_run_stage`, between the `compile` and `diff` branches:
```python
    elif name == "index":
        index.run(
            wiki_dir=root / "wiki",
            categories=categories,
        )
```

The `categories` variable is already loaded at the top of `_run_stage` via `load_categories(root / "config" / "categories.yaml")`.

- [ ] **Step 4: Run the new test and the full main_cli suite**

Run: `uv run pytest tests/test_main_cli.py -v`
Expected: 5 passed (4 existing + new index acceptance).

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: 0 failures. Total test count after Task 1 (10 new), Task 2 (3 new), and Task 3 (1 new) = baseline + 14.

- [ ] **Step 6: Verify CLI help shows the new stage**

Run: `uv run python -m pipeline.main --help`
Expected: `--stage` choice list contains `index` between `compile` and `diff`.

- [ ] **Step 7: Ruff lint + format**

Run: `uv run ruff check pipeline/main.py tests/test_main_cli.py`
Run: `uv run ruff format --check pipeline/main.py tests/test_main_cli.py`

Auto-fix with `uv run ruff format ...` if needed.

- [ ] **Step 8: Commit**

```bash
git add pipeline/main.py tests/test_main_cli.py
git commit -m "feat(cli): register index stage between compile and diff"
```

---

## Task 4: Run on actual wiki and commit generated READMEs

**Files:**
- New: `wiki/README.md` (auto-generated)
- New: `wiki/01-principles/README.md` (auto-generated)
- New: `wiki/02-rule-stage/README.md` (auto-generated)
- New: `wiki/03-weapon-role/README.md` (auto-generated)
- Existing categories with no current pages also get a README. (`04-stepup`, `05-glossary`)

This task does NOT use TDD — it runs the stage against the real `wiki/` content already in the repo.

- [ ] **Step 1: Run the index stage**

Run: `uv run python -m pipeline.main --stage index`
Expected: stdout includes `[pipeline] running stage: index`. Exits 0.

- [ ] **Step 2: Inspect generated files**

Run: `git status --short wiki/`
Expected: list shows new `wiki/README.md` and new `wiki/<category>/README.md` files.

Run: `cat wiki/README.md`
Expected: matches the format from the spec — title, intro, category list with counts.

Run: `cat wiki/01-principles/README.md` (or any populated category)
Expected: page list with title + summary lines.

- [ ] **Step 3: Run the diff stage so the new READMEs land in a proper "wiki:" commit**

Run: `uv run python -m pipeline.main --stage diff`
Expected: creates a commit with message `wiki: regenerate pages` (the existing diff_commit default message).

Run: `git log --oneline -1`
Expected: shows the new wiki commit.

- [ ] **Step 4: Verify final test suite still green**

Run: `uv run pytest -q`
Expected: all tests pass.

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

---

## Completion checklist

- [ ] Task 1-4 committed
- [ ] `wiki/README.md` exists and lists all 5 categories with their page counts
- [ ] Each populated category has a `wiki/<cat>/README.md` listing its pages with title + summary
- [ ] Empty categories (`04-stepup`, `05-glossary`) have a README showing "(まだページがありません)"
- [ ] `uv run pytest` — all green
- [ ] `uv run ruff check . && uv run ruff format --check .` — clean
- [ ] `uv run python -m pipeline.main --all` runs `index` between `compile` and `diff` (verify by running once and confirming logs)
