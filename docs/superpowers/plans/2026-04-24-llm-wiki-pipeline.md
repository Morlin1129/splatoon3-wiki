# LLM Wiki Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python pipeline that turns raw Splatoon-related markdown sources (chat logs, meeting notes) into compiled Wiki pages under a MECE category system, with pluggable LLM providers and incremental regeneration.

**Architecture:** Five-stage pipeline (Ingest → Classify → Cluster → Compile → Diff) with markdown intermediates between stages. Three stages call LLMs through a pluggable `LLMProvider` Protocol; two stages are pure code. State is tracked in a JSON manifest so reruns only touch changed inputs.

**Tech Stack:** Python 3.12+, `uv` (deps), `pydantic` (schemas), `python-frontmatter` (MD IO), `pyyaml` (config), `anthropic`, `google-genai`, `pytest`, `ruff`.

**Spec reference:** `docs/superpowers/specs/2026-04-23-llm-wiki-pipeline-design.md`

---

## File Structure

**New files** (created by this plan):

```
pyproject.toml
.env.example
.python-version
config/
  categories.yaml                # Fixed top-level categories (① through ⑤)
  pipeline.yaml                  # Per-stage provider/model selection
pipeline/
  __init__.py
  config.py                      # Load & validate config YAMLs
  models.py                      # Pydantic models for MD frontmatter
  frontmatter_io.py              # Read/write MD with validated frontmatter
  state.py                       # ingest_manifest.json read/write helpers
  slug.py                        # Slugify helper for subtopic names
  llm/
    __init__.py
    base.py                      # LLMProvider Protocol + factory
    anthropic_provider.py
    gemini_provider.py
    fake.py                      # FakeLLMProvider for tests
  stages/
    __init__.py
    ingest.py
    classify.py
    cluster.py
    compile.py
    diff_commit.py
  prompts/
    ingest.md
    classify.md
    compile.md
  main.py                        # CLI entrypoint
sample_raw/
  2026-04-01-meeting-notes.md
  2026-04-05-discord-log.md
tests/
  __init__.py
  conftest.py
  test_config.py
  test_frontmatter_io.py
  test_state.py
  test_slug.py
  test_llm_fake.py
  test_llm_factory.py
  stages/
    __init__.py
    test_ingest.py
    test_classify.py
    test_cluster.py
    test_compile.py
    test_diff_commit.py
  test_main_cli.py
  test_end_to_end.py             # Pipeline with FakeLLMProvider
```

**Modified files:** None (this is the initial build).

**Each file's responsibility:**
- `config.py` — single source of truth for loading `config/*.yaml`
- `models.py` — pydantic schemas used by all stages for frontmatter
- `frontmatter_io.py` — isolates `python-frontmatter` usage; pure functions
- `state.py` — owns `state/ingest_manifest.json` structure
- `llm/base.py` — defines the `LLMProvider` Protocol + `get_provider()` factory
- `llm/{anthropic,gemini,fake}_provider.py` — one Protocol impl each
- `stages/*.py` — one stage per file; each exposes `run(config, ...) -> None`
- `main.py` — argparse CLI that dispatches to stages
- `prompts/*.md` — plaintext system prompts loaded at runtime

---

## Task 1: Project scaffolding and dev tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.env.example`
- Create: `pipeline/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/stages/__init__.py`

- [ ] **Step 1: Write `.python-version`**

```
3.12
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "splatoon3-wiki-pipeline"
version = "0.1.0"
description = "LLM Wiki generation pipeline for splatoon3-wiki"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40.0",
    "google-genai>=0.3.0",
    "pydantic>=2.8.0",
    "python-frontmatter>=1.1.0",
    "pyyaml>=6.0.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.6.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "RUF"]
```

- [ ] **Step 3: Write `.env.example`**

```
# Anthropic API key for Claude (Stage 4: Compile)
ANTHROPIC_API_KEY=

# Google Gen AI API key for Gemini (Stage 1: Ingest, Stage 2: Classify)
GEMINI_API_KEY=
```

- [ ] **Step 4: Create empty `__init__.py` files**

Create three empty files:
```
pipeline/__init__.py
tests/__init__.py
tests/stages/__init__.py
```

- [ ] **Step 5: Install and verify**

Run: `cd "$(git rev-parse --show-toplevel)" && uv sync --extra dev`
Expected: completes without error, creates `.venv/` and `uv.lock`.

Run: `uv run python -c "import anthropic, google.genai, pydantic, frontmatter, yaml, pytest, ruff"`
Expected: exits 0 with no output (all deps importable).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version .env.example uv.lock pipeline/__init__.py tests/__init__.py tests/stages/__init__.py
git commit -m "chore: scaffold Python project with uv, pytest, ruff"
```

---

## Task 2: Config loading and validation

**Files:**
- Create: `config/categories.yaml`
- Create: `config/pipeline.yaml`
- Create: `pipeline/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from pathlib import Path

import pytest

from pipeline.config import Category, PipelineConfig, StageConfig, load_categories, load_pipeline


def test_load_categories(tmp_path: Path) -> None:
    yaml_path = tmp_path / "categories.yaml"
    yaml_path.write_text(
        "categories:\n"
        "  - id: 01-principles\n"
        "    label: 原理原則\n"
        "    description: 普遍理論\n"
        "  - id: 02-rule-stage\n"
        "    label: ルール×ステージ\n"
        "    description: 定石\n",
        encoding="utf-8",
    )

    result = load_categories(yaml_path)

    assert result == [
        Category(id="01-principles", label="原理原則", description="普遍理論"),
        Category(id="02-rule-stage", label="ルール×ステージ", description="定石"),
    ]


def test_load_pipeline(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(
        "stages:\n"
        "  ingest:\n"
        "    provider: gemini\n"
        "    model: gemini-2.5-flash\n"
        "    max_tokens: 4096\n"
        "  classify:\n"
        "    provider: gemini\n"
        "    model: gemini-2.5-flash\n"
        "    max_tokens: 512\n"
        "  compile:\n"
        "    provider: anthropic\n"
        "    model: claude-sonnet-4-6\n"
        "    max_tokens: 8192\n",
        encoding="utf-8",
    )

    result = load_pipeline(yaml_path)

    assert isinstance(result, PipelineConfig)
    assert result.stages["ingest"] == StageConfig(
        provider="gemini", model="gemini-2.5-flash", max_tokens=4096
    )
    assert result.stages["compile"].provider == "anthropic"


def test_load_pipeline_rejects_unknown_provider(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(
        "stages:\n"
        "  ingest:\n"
        "    provider: bogus\n"
        "    model: x\n"
        "    max_tokens: 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="provider"):
        load_pipeline(yaml_path)
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.config'`.

- [ ] **Step 3: Implement `pipeline/config.py`**

```python
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Provider = Literal["anthropic", "gemini", "fake"]


class Category(BaseModel):
    id: str
    label: str
    description: str


class StageConfig(BaseModel):
    provider: Provider
    model: str
    max_tokens: int = Field(gt=0)


class PipelineConfig(BaseModel):
    stages: dict[str, StageConfig]


def load_categories(path: Path) -> list[Category]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Category.model_validate(item) for item in data["categories"]]


def load_pipeline(path: Path) -> PipelineConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PipelineConfig.model_validate(data)
```

- [ ] **Step 4: Write real config files**

`config/categories.yaml`:
```yaml
categories:
  - id: 01-principles
    label: 原理原則
    description: ルール・ステージ・ブキ非依存の普遍理論
  - id: 02-rule-stage
    label: ルール×ステージ
    description: ルール×ステージ固有の定石
  - id: 03-weapon-role
    label: ブキ・役割
    description: ブキ／サブ／スペシャル／ロール固有のノウハウ（ギアパワー構成含む）
  - id: 04-stepup
    label: ステップアップガイド
    description: XP1800-2400 向けに ①②③ から抽出したエッセンス集
  - id: 05-glossary
    label: 用語集
    description: スプラトゥーン用語／FPS・TPS 用語
```

`config/pipeline.yaml`:
```yaml
stages:
  ingest:
    provider: gemini
    model: gemini-2.5-flash
    max_tokens: 4096
  classify:
    provider: gemini
    model: gemini-2.5-flash
    max_tokens: 512
  compile:
    provider: anthropic
    model: claude-sonnet-4-6
    max_tokens: 8192
```

- [ ] **Step 5: Run test and verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add config/ pipeline/config.py tests/test_config.py
git commit -m "feat(config): add pydantic-validated YAML loaders for categories and pipeline"
```

---

## Task 3: Frontmatter models

**Files:**
- Create: `pipeline/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from datetime import datetime

import pytest
from pydantic import ValidationError

from pipeline.models import ClassifiedFrontmatter, SnippetFrontmatter, WikiFrontmatter


def test_snippet_frontmatter_minimum_fields() -> None:
    fm = SnippetFrontmatter(
        source_file="sample_raw/2026-04-01-meeting-notes.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="abc123",
    )

    assert fm.source_file.endswith(".md")
    assert fm.content_hash == "abc123"


def test_classified_frontmatter_requires_category_and_subtopic() -> None:
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="abc123",
        category="02-rule-stage",
        subtopic="海女美術_ガチエリア",
    )

    assert fm.category == "02-rule-stage"

    with pytest.raises(ValidationError):
        ClassifiedFrontmatter(
            source_file="x.md",
            source_date="2026-04-01",
            extracted_at=datetime(2026, 4, 24, 12, 0, 0),
            content_hash="abc123",
            category="",  # empty rejected
            subtopic="x",
        )


def test_wiki_frontmatter_sources_list() -> None:
    fm = WikiFrontmatter(
        category="02-rule-stage",
        subtopic="海女美術_ガチエリア",
        sources=[
            "https://drive.google.com/file/d/AAA",
            "https://drive.google.com/file/d/BBB",
        ],
        updated_at=datetime(2026, 4, 24, 12, 0, 0),
    )

    assert len(fm.sources) == 2
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.models'`.

- [ ] **Step 3: Implement `pipeline/models.py`**

```python
from datetime import datetime

from pydantic import BaseModel, Field


class SnippetFrontmatter(BaseModel):
    source_file: str = Field(min_length=1)
    source_date: str = Field(min_length=1)
    extracted_at: datetime
    content_hash: str = Field(min_length=1)


class ClassifiedFrontmatter(SnippetFrontmatter):
    category: str = Field(min_length=1)
    subtopic: str = Field(min_length=1)


class WikiFrontmatter(BaseModel):
    category: str = Field(min_length=1)
    subtopic: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    updated_at: datetime
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py tests/test_models.py
git commit -m "feat(models): add pydantic frontmatter schemas for snippet/classified/wiki"
```

---

## Task 4: Frontmatter IO helpers

**Files:**
- Create: `pipeline/frontmatter_io.py`
- Create: `tests/test_frontmatter_io.py`

- [ ] **Step 1: Write the failing test**

`tests/test_frontmatter_io.py`:
```python
from datetime import datetime
from pathlib import Path

from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.models import SnippetFrontmatter


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    fm = SnippetFrontmatter(
        source_file="sample_raw/x.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="hash_123",
    )
    target = tmp_path / "snippet.md"
    body = "右高台の制圧は味方の復帰を遅らせるリスクがある。"

    write_frontmatter(target, fm, body)

    loaded_fm, loaded_body = read_frontmatter(target, SnippetFrontmatter)
    assert loaded_fm == fm
    assert loaded_body.strip() == body


def test_read_plain_markdown_without_frontmatter(tmp_path: Path) -> None:
    target = tmp_path / "plain.md"
    target.write_text("# Just body\n\nNo frontmatter.\n", encoding="utf-8")

    _, body = read_frontmatter(target, SnippetFrontmatter, require=False)

    assert body.strip().startswith("# Just body")
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_frontmatter_io.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/frontmatter_io.py`**

```python
from pathlib import Path
from typing import TypeVar

import frontmatter
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def write_frontmatter(path: Path, fm: BaseModel, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body, **fm.model_dump(mode="json"))
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def read_frontmatter(
    path: Path, model: type[T], *, require: bool = True
) -> tuple[T | None, str]:
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    body = post.content
    if not post.metadata:
        if require:
            raise ValueError(f"{path} has no frontmatter")
        return None, body
    return model.model_validate(post.metadata), body
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/test_frontmatter_io.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/frontmatter_io.py tests/test_frontmatter_io.py
git commit -m "feat(frontmatter): add validated read/write helpers for MD frontmatter"
```

---

## Task 5: Slug helper

**Files:**
- Create: `pipeline/slug.py`
- Create: `tests/test_slug.py`

- [ ] **Step 1: Write the failing test**

`tests/test_slug.py`:
```python
from pipeline.slug import slugify


def test_slugify_ascii() -> None:
    assert slugify("Hello World") == "hello-world"


def test_slugify_preserves_japanese_but_strips_punctuation() -> None:
    assert slugify("海女美術大学 ガチエリア") == "海女美術大学-ガチエリア"
    assert slugify("2 落ち!!") == "2-落ち"


def test_slugify_collapses_whitespace() -> None:
    assert slugify("  a   b  c ") == "a-b-c"


def test_slugify_empty_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        slugify("   ")
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_slug.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/slug.py`**

```python
import re
import unicodedata


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"[\s/]+", "-", text)
    # Keep word chars (includes CJK via Python's Unicode-aware \w) and hyphens
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        raise ValueError("slug cannot be empty")
    return text
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/test_slug.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/slug.py tests/test_slug.py
git commit -m "feat(slug): add slugify helper preserving CJK characters"
```

---

## Task 6: State manifest helpers

**Files:**
- Create: `pipeline/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
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
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/state.py`**

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

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            raw=data.get("raw", {}),
            snippets=data.get("snippets", {}),
            wiki=data.get("wiki", {}),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"raw": self.raw, "snippets": self.snippets, "wiki": self.wiki},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/test_state.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/state.py tests/test_state.py
git commit -m "feat(state): add Manifest dataclass with JSON roundtrip"
```

---

## Task 7: LLM provider base, fake, and factory

**Files:**
- Create: `pipeline/llm/__init__.py`
- Create: `pipeline/llm/base.py`
- Create: `pipeline/llm/fake.py`
- Create: `tests/test_llm_fake.py`
- Create: `tests/test_llm_factory.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_llm_fake.py`:
```python
from pipeline.llm.fake import FakeLLMProvider


def test_fake_returns_canned_responses_in_order() -> None:
    provider = FakeLLMProvider(responses=["first", "second"])
    assert provider.complete(system="s", user="u", model="m", max_tokens=10) == "first"
    assert provider.complete(system="s", user="u", model="m", max_tokens=10) == "second"


def test_fake_records_calls() -> None:
    provider = FakeLLMProvider(responses=["only"])
    provider.complete(system="sys", user="usr", model="mdl", max_tokens=7)

    assert provider.calls[0].system == "sys"
    assert provider.calls[0].user == "usr"
    assert provider.calls[0].model == "mdl"
    assert provider.calls[0].max_tokens == 7


def test_fake_raises_when_exhausted() -> None:
    import pytest

    provider = FakeLLMProvider(responses=[])
    with pytest.raises(AssertionError, match="exhausted"):
        provider.complete(system="s", user="u", model="m", max_tokens=1)
```

`tests/test_llm_factory.py`:
```python
import pytest

from pipeline.config import StageConfig
from pipeline.llm.base import get_provider
from pipeline.llm.fake import FakeLLMProvider


def test_get_provider_returns_fake_instance() -> None:
    cfg = StageConfig(provider="fake", model="irrelevant", max_tokens=1)
    provider = get_provider(cfg, fake_responses=["ok"])

    assert isinstance(provider, FakeLLMProvider)


def test_get_provider_raises_for_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = StageConfig(provider="anthropic", model="claude-sonnet-4-6", max_tokens=100)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_provider(cfg)
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/test_llm_fake.py tests/test_llm_factory.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/llm/__init__.py`**

```python
```

(empty file)

- [ ] **Step 4: Implement `pipeline/llm/base.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Protocol

from pipeline.config import StageConfig

ResponseFormat = Literal["text", "json"]


class LLMProvider(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: ResponseFormat = "text",
    ) -> str: ...


@dataclass
class CallRecord:
    system: str
    user: str
    model: str
    max_tokens: int
    response_format: ResponseFormat


def get_provider(
    cfg: StageConfig, *, fake_responses: list[str] | None = None
) -> LLMProvider:
    if cfg.provider == "fake":
        from pipeline.llm.fake import FakeLLMProvider

        return FakeLLMProvider(responses=fake_responses or [])
    if cfg.provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from pipeline.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if cfg.provider == "gemini":
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY not set")
        from pipeline.llm.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise ValueError(f"unknown provider: {cfg.provider}")
```

- [ ] **Step 5: Implement `pipeline/llm/fake.py`**

```python
from __future__ import annotations

from pipeline.llm.base import CallRecord, ResponseFormat


class FakeLLMProvider:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[CallRecord] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: ResponseFormat = "text",
    ) -> str:
        self.calls.append(
            CallRecord(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        )
        assert self._responses, "FakeLLMProvider response queue exhausted"
        return self._responses.pop(0)
```

- [ ] **Step 6: Run tests and verify they pass**

Run: `uv run pytest tests/test_llm_fake.py tests/test_llm_factory.py -v`
Expected: 5 passed (importing anthropic/gemini providers will fail inside factory — those tests will skip via monkeypatch).

Note: the `test_get_provider_raises_for_missing_api_key` test clears `ANTHROPIC_API_KEY` before calling. The factory raises before importing the anthropic provider module.

- [ ] **Step 7: Commit**

```bash
git add pipeline/llm/__init__.py pipeline/llm/base.py pipeline/llm/fake.py tests/test_llm_fake.py tests/test_llm_factory.py
git commit -m "feat(llm): add LLMProvider Protocol, FakeLLMProvider, and factory"
```

---

## Task 8: Anthropic provider implementation

**Files:**
- Create: `pipeline/llm/anthropic_provider.py`
- Create: `tests/test_anthropic_provider.py`

- [ ] **Step 1: Write the failing test (monkeypatched SDK)**

`tests/test_anthropic_provider.py`:
```python
from types import SimpleNamespace

import pytest


def _make_mock_client(captured: dict) -> SimpleNamespace:
    class MockMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="mocked reply")])

    return SimpleNamespace(messages=MockMessages())


def test_anthropic_provider_passes_arguments_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    import pipeline.llm.anthropic_provider as mod

    monkeypatch.setattr(mod, "_build_client", lambda: _make_mock_client(captured))
    provider = mod.AnthropicProvider()

    out = provider.complete(
        system="sys prompt",
        user="user prompt",
        model="claude-sonnet-4-6",
        max_tokens=1024,
    )

    assert out == "mocked reply"
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["max_tokens"] == 1024
    assert captured["system"] == "sys prompt"
    assert captured["messages"] == [{"role": "user", "content": "user prompt"}]
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_anthropic_provider.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/llm/anthropic_provider.py`**

```python
from __future__ import annotations

import os

import anthropic

from pipeline.llm.base import ResponseFormat


def _build_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


class AnthropicProvider:
    def __init__(self) -> None:
        self._client = _build_client()

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: ResponseFormat = "text",
    ) -> str:
        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/test_anthropic_provider.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm/anthropic_provider.py tests/test_anthropic_provider.py
git commit -m "feat(llm): add Anthropic provider implementation with mockable client"
```

---

## Task 9: Gemini provider implementation

**Files:**
- Create: `pipeline/llm/gemini_provider.py`
- Create: `tests/test_gemini_provider.py`

- [ ] **Step 1: Write the failing test**

`tests/test_gemini_provider.py`:
```python
from types import SimpleNamespace

import pytest


def _make_mock_client(captured: dict) -> SimpleNamespace:
    class MockModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="gemini mock reply")

    return SimpleNamespace(models=MockModels())


def test_gemini_provider_passes_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    import pipeline.llm.gemini_provider as mod

    monkeypatch.setattr(mod, "_build_client", lambda: _make_mock_client(captured))
    provider = mod.GeminiProvider()

    out = provider.complete(
        system="sys prompt",
        user="user prompt",
        model="gemini-2.5-flash",
        max_tokens=512,
    )

    assert out == "gemini mock reply"
    assert captured["model"] == "gemini-2.5-flash"
    # google-genai passes system + user via config and contents respectively
    assert "user prompt" in str(captured["contents"])
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_gemini_provider.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/llm/gemini_provider.py`**

```python
from __future__ import annotations

import os

from google import genai
from google.genai import types as genai_types

from pipeline.llm.base import ResponseFormat


def _build_client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


class GeminiProvider:
    def __init__(self) -> None:
        self._client = _build_client()

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: ResponseFormat = "text",
    ) -> str:
        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if response_format == "json" else "text/plain",
        )
        response = self._client.models.generate_content(
            model=model,
            contents=user,
            config=config,
        )
        return response.text
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/test_gemini_provider.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm/gemini_provider.py tests/test_gemini_provider.py
git commit -m "feat(llm): add Gemini provider implementation"
```

---

## Task 10: Sample raw data and system prompts

**Files:**
- Create: `sample_raw/2026-04-01-meeting-notes.md`
- Create: `sample_raw/2026-04-05-discord-log.md`
- Create: `pipeline/prompts/ingest.md`
- Create: `pipeline/prompts/classify.md`
- Create: `pipeline/prompts/compile.md`

- [ ] **Step 1: Write sample raw MD files**

`sample_raw/2026-04-01-meeting-notes.md`:
```markdown
# チーム練習メモ 2026-04-01

今日の気づき。

- 海女美術大学のガチエリアで右高台を取りに行く動きを練習した。ただ取ったあとに人数不利で崩される場面が複数回あった。キルが入ったら前線を上げる、取れなかったらヘイトを残して退く、の判断を早くしたい。
- シャープマーカーでキューインクボムを投げるタイミングが遅い。カニタンクに合わせる前提でスペシャルを貯めたい。
- 2 落ち状態で前線維持を試みて崩壊するケースが頻発。人数不利時はオブジェクト関与より復帰ルートの優先度を上げる。
```

`sample_raw/2026-04-05-discord-log.md`:
```markdown
# Discord 雑談ログ 2026-04-05

(実名は sanitize 済みのサンプル)

- 「激ロー」ってスプラでも使うのか気になった。スプラ界隈だと「イカ状態で物陰から奇襲」くらいの意味らしい。
- マテガイ放水路のガチホコ、リスポーン復帰で右ルートを使うと時間ロスが大きい。左の細い通路を抜けたほうが早い。
- スペシャルのカニタンクは単独だと溶ける。ウルショかメガホンと合わせると制圧力が跳ねる。
```

- [ ] **Step 2: Write `pipeline/prompts/ingest.md`**

```markdown
You are a knowledge extractor for a Splatoon 3 wiki.

Input: a single raw markdown document (meeting notes, Discord chat log, or coaching record).

Task: extract ONLY the universal, reusable knowledge items from the input. Strip all personal names, Discord handles, and any content that is tied to a specific individual. Rewrite individual coaching feedback as universal principles.

Output: a JSON array. Each element is an object with two fields:
- `slug`: short kebab-case identifier in English (e.g. `amabi-zone-right-high`)
- `content`: the extracted knowledge as a short paragraph of Japanese prose

Rules:
- No personal names, handles, or team-specific jargon that identifies individuals
- One knowledge item per array element
- Each `content` should be self-contained (readable without the source)
- If the input contains no knowledge items, return `[]`

Respond with JSON only, no prose wrapper.
```

- [ ] **Step 3: Write `pipeline/prompts/classify.md`**

````markdown
You classify a Splatoon 3 wiki snippet into a fixed category and a subtopic.

You will receive:
- The list of top-level categories (id, label, description) as a YAML block
- The snippet body

Task: choose exactly one category id, and invent a short subtopic slug that groups related snippets. Reuse existing subtopic slugs when possible (they will be provided in the input).

Output JSON only, on a single line, in this shape:
`{"category": "<category-id>", "subtopic": "<subtopic-slug>"}`

Rules:
- `category` MUST be one of the provided ids
- `subtopic` uses lowercase kebab-case; Japanese characters may appear if needed (e.g. `海女美術-ガチエリア`)
- No prose, no explanation, no code fences
````

- [ ] **Step 4: Write `pipeline/prompts/compile.md`**

```markdown
You compose a Splatoon 3 wiki page from a set of snippets on the same subtopic.

You will receive:
- The category label and subtopic name
- A numbered list of snippet bodies (Japanese)

Task: produce a well-structured Japanese markdown page. Include:
- A short intro (2-3 sentences)
- Section headings as needed (use `##`)
- Bullet points where appropriate
- A closing "要点" section summarizing the top 3 takeaways

Rules:
- Do NOT include any frontmatter (the pipeline adds it)
- Do NOT include source URLs (the pipeline appends them)
- Do NOT invent facts not present in the snippets
- Natural Japanese prose, concise and actionable
```

- [ ] **Step 5: Verify files exist**

Run: `ls sample_raw pipeline/prompts`
Expected: both directories listed with the new files.

- [ ] **Step 6: Commit**

```bash
git add sample_raw/ pipeline/prompts/
git commit -m "chore: add sample raw data and system prompts for each LLM stage"
```

---

## Task 11: Stage 1 — Ingest

**Files:**
- Create: `pipeline/stages/__init__.py`
- Create: `pipeline/stages/ingest.py`
- Create: `tests/stages/test_ingest.py`

- [ ] **Step 1: Write the failing test**

`tests/stages/test_ingest.py`:
```python
import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import StageConfig
from pipeline.frontmatter_io import read_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import SnippetFrontmatter
from pipeline.stages import ingest
from pipeline.state import Manifest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "sample_raw").mkdir()
    (tmp_path / "snippets").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "pipeline" / "prompts").mkdir(parents=True)
    (tmp_path / "pipeline" / "prompts" / "ingest.md").write_text(
        "INGEST PROMPT", encoding="utf-8"
    )
    return tmp_path


def test_ingest_creates_snippet_files(workspace: Path) -> None:
    raw = workspace / "sample_raw" / "2026-04-01-notes.md"
    raw.write_text("# Notes\n\n右高台の制圧は…", encoding="utf-8")

    llm_response = json.dumps(
        [
            {"slug": "right-high-control", "content": "右高台の制圧はリスクあり。"},
            {"slug": "two-down-retreat", "content": "2 落ちしたら退く。"},
        ],
        ensure_ascii=False,
    )
    provider = FakeLLMProvider(responses=[llm_response])

    stage_cfg = StageConfig(provider="fake", model="x", max_tokens=4096)
    ingest.run(
        provider=provider,
        stage_cfg=stage_cfg,
        raw_dir=workspace / "sample_raw",
        snippets_dir=workspace / "snippets",
        manifest_path=workspace / "state" / "ingest_manifest.json",
        prompt_path=workspace / "pipeline" / "prompts" / "ingest.md",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
    )

    snippets = sorted((workspace / "snippets").glob("*.md"))
    assert len(snippets) == 2

    fm, body = read_frontmatter(snippets[0], SnippetFrontmatter)
    assert fm.source_file.endswith("2026-04-01-notes.md")
    assert fm.source_date == "2026-04-01"
    assert fm.extracted_at == datetime(2026, 4, 24, 12, 0, 0)
    assert body.strip() in {"右高台の制圧はリスクあり。", "2 落ちしたら退く。"}


def test_ingest_skips_unchanged_raw(workspace: Path) -> None:
    raw = workspace / "sample_raw" / "2026-04-01-notes.md"
    raw.write_text("# Notes", encoding="utf-8")

    manifest_path = workspace / "state" / "ingest_manifest.json"
    import hashlib

    h = hashlib.sha256(raw.read_bytes()).hexdigest()
    manifest = Manifest(raw={str(raw.relative_to(workspace)): {"content_hash": h}})
    manifest.save(manifest_path)

    provider = FakeLLMProvider(responses=[])  # will assert if called

    stage_cfg = StageConfig(provider="fake", model="x", max_tokens=4096)
    ingest.run(
        provider=provider,
        stage_cfg=stage_cfg,
        raw_dir=workspace / "sample_raw",
        snippets_dir=workspace / "snippets",
        manifest_path=manifest_path,
        prompt_path=workspace / "pipeline" / "prompts" / "ingest.md",
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=workspace,
    )

    assert provider.calls == []  # no LLM call since nothing changed
    assert list((workspace / "snippets").glob("*.md")) == []
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/stages/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError` for `pipeline.stages`.

- [ ] **Step 3: Implement `pipeline/stages/__init__.py`**

```python
```

(empty file)

- [ ] **Step 4: Implement `pipeline/stages/ingest.py`**

```python
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pipeline.config import StageConfig
from pipeline.frontmatter_io import write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.models import SnippetFrontmatter
from pipeline.slug import slugify
from pipeline.state import Manifest

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _source_date(path: Path) -> str:
    m = _DATE_PREFIX.match(path.name)
    if m:
        return m.group(1)
    return datetime.utcnow().strftime("%Y-%m-%d")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_llm_response(text: str) -> list[dict]:
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("ingest LLM response must be a JSON array")
    return data


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    raw_dir: Path,
    snippets_dir: Path,
    manifest_path: Path,
    prompt_path: Path,
    now: Callable[[], datetime] = datetime.utcnow,
    root: Path | None = None,
) -> None:
    root = root or raw_dir.parent
    manifest = Manifest.load(manifest_path)
    system_prompt = prompt_path.read_text(encoding="utf-8")

    for raw_file in sorted(raw_dir.glob("*.md")):
        rel = str(raw_file.relative_to(root))
        file_hash = _hash_file(raw_file)

        prior = manifest.raw.get(rel)
        if prior and prior.get("content_hash") == file_hash:
            continue  # no change, skip LLM call

        body = raw_file.read_text(encoding="utf-8")
        reply = provider.complete(
            system=system_prompt,
            user=body,
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        items = _parse_llm_response(reply)
        src_date = _source_date(raw_file)
        extracted_at = now()

        for item in items:
            slug = slugify(item["slug"])
            out_path = snippets_dir / f"{src_date}-{slug}.md"
            fm = SnippetFrontmatter(
                source_file=rel,
                source_date=src_date,
                extracted_at=extracted_at,
                content_hash=file_hash,
            )
            write_frontmatter(out_path, fm, item["content"])
            manifest.snippets[str(out_path.relative_to(root))] = {
                "source_hash": file_hash,
                "classified": False,
            }

        manifest.raw[rel] = {
            "content_hash": file_hash,
            "ingested_at": extracted_at.isoformat(),
        }

    manifest.save(manifest_path)
```

- [ ] **Step 5: Run test and verify it passes**

Run: `uv run pytest tests/stages/test_ingest.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/__init__.py pipeline/stages/ingest.py tests/stages/test_ingest.py
git commit -m "feat(stages): add Ingest stage that extracts snippet MDs from raw sources"
```

---

## Task 12: Stage 2 — Classify

**Files:**
- Create: `pipeline/stages/classify.py`
- Create: `tests/stages/test_classify.py`

- [ ] **Step 1: Write the failing test**

`tests/stages/test_classify.py`:
```python
import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category, StageConfig
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
    (tmp_path / "pipeline" / "prompts").mkdir(parents=True)
    (tmp_path / "pipeline" / "prompts" / "classify.md").write_text(
        "CLASSIFY PROMPT", encoding="utf-8"
    )
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


def test_classify_moves_snippet_to_classified_dir(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "2026-04-01-abc.md", "右高台の制圧はリスク…")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    manifest = Manifest(
        snippets={str(snippet_path.relative_to(workspace)): {"source_hash": "h1", "classified": False}},
    )
    manifest.save(manifest_path)

    categories = [
        Category(id="01-principles", label="原理原則", description="..."),
        Category(id="02-rule-stage", label="ルール×ステージ", description="..."),
    ]

    provider = FakeLLMProvider(
        responses=[json.dumps({"category": "02-rule-stage", "subtopic": "海女美術-ガチエリア"})]
    )
    stage_cfg = StageConfig(provider="fake", model="x", max_tokens=512)

    classify.run(
        provider=provider,
        stage_cfg=stage_cfg,
        categories=categories,
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        prompt_path=workspace / "pipeline" / "prompts" / "classify.md",
        root=workspace,
    )

    out = workspace / "classified" / "02-rule-stage" / "2026-04-01-abc.md"
    assert out.exists()
    fm, body = read_frontmatter(out, ClassifiedFrontmatter)
    assert fm.category == "02-rule-stage"
    assert fm.subtopic == "海女美術-ガチエリア"
    assert "右高台" in body

    reloaded = Manifest.load(manifest_path)
    assert reloaded.snippets[str(snippet_path.relative_to(workspace))]["classified"] is True


def test_classify_skips_already_classified(workspace: Path) -> None:
    snippet_path = _seed_snippet(workspace, "2026-04-01-abc.md", "…")
    manifest_path = workspace / "state" / "ingest_manifest.json"
    manifest = Manifest(
        snippets={str(snippet_path.relative_to(workspace)): {"source_hash": "h1", "classified": True}},
    )
    manifest.save(manifest_path)

    provider = FakeLLMProvider(responses=[])
    classify.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=512),
        categories=[Category(id="01-principles", label="x", description="y")],
        snippets_dir=workspace / "snippets",
        classified_dir=workspace / "classified",
        manifest_path=manifest_path,
        prompt_path=workspace / "pipeline" / "prompts" / "classify.md",
        root=workspace,
    )

    assert provider.calls == []
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/stages/test_classify.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/stages/classify.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

from pipeline.config import Category, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.models import ClassifiedFrontmatter, SnippetFrontmatter
from pipeline.state import Manifest


def _build_user_prompt(
    categories: list[Category], snippet_body: str, known_subtopics: list[str]
) -> str:
    cat_yaml = yaml.safe_dump(
        {"categories": [c.model_dump() for c in categories]},
        allow_unicode=True,
        sort_keys=False,
    )
    known = "\n".join(f"- {s}" for s in sorted(set(known_subtopics))) or "(none yet)"
    return (
        f"{cat_yaml}\n\n"
        f"Existing subtopics (reuse when appropriate):\n{known}\n\n"
        f"Snippet body:\n---\n{snippet_body}\n---"
    )


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    snippets_dir: Path,
    classified_dir: Path,
    manifest_path: Path,
    prompt_path: Path,
    root: Path,
) -> None:
    manifest = Manifest.load(manifest_path)
    system_prompt = prompt_path.read_text(encoding="utf-8")
    valid_ids = {c.id for c in categories}

    known_subtopics = [
        p.stem for cat_dir in classified_dir.glob("*/") for p in cat_dir.glob("*.md")
    ]

    for snippet_path in sorted(snippets_dir.glob("*.md")):
        rel = str(snippet_path.relative_to(root))
        entry = manifest.snippets.get(rel)
        if entry and entry.get("classified"):
            continue

        fm, body = read_frontmatter(snippet_path, SnippetFrontmatter)
        assert fm is not None

        user = _build_user_prompt(categories, body, known_subtopics)
        reply = provider.complete(
            system=system_prompt,
            user=user,
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
            response_format="json",
        )
        parsed = json.loads(reply)
        category_id = parsed["category"]
        subtopic = parsed["subtopic"]
        if category_id not in valid_ids:
            raise ValueError(f"classify returned unknown category {category_id}")

        classified_fm = ClassifiedFrontmatter(
            **fm.model_dump(),
            category=category_id,
            subtopic=subtopic,
        )
        out = classified_dir / category_id / snippet_path.name
        write_frontmatter(out, classified_fm, body)
        known_subtopics.append(subtopic)

        if rel in manifest.snippets:
            manifest.snippets[rel]["classified"] = True
        else:
            manifest.snippets[rel] = {"source_hash": fm.content_hash, "classified": True}

    manifest.save(manifest_path)
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/stages/test_classify.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/stages/classify.py tests/stages/test_classify.py
git commit -m "feat(stages): add Classify stage assigning category and subtopic to snippets"
```

---

## Task 13: Stage 3 — Cluster

**Files:**
- Create: `pipeline/stages/cluster.py`
- Create: `tests/stages/test_cluster.py`

- [ ] **Step 1: Write the failing test**

`tests/stages/test_cluster.py`:
```python
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
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/stages/test_cluster.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/stages/cluster.py`**

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
        assert fm is not None
        key = f"{fm.category}/{fm.subtopic}"
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

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/stages/test_cluster.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/stages/cluster.py tests/stages/test_cluster.py
git commit -m "feat(stages): add Cluster stage aggregating classified snippets by subtopic"
```

---

## Task 14: Stage 4 — Compile

**Files:**
- Create: `pipeline/stages/compile.py`
- Create: `tests/stages/test_compile.py`

- [ ] **Step 1: Write the failing test**

`tests/stages/test_compile.py`:
```python
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.config import Category, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.fake import FakeLLMProvider
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.stages import compile as compile_stage
from pipeline.state import Manifest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "classified" / "02-rule-stage").mkdir(parents=True)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "pipeline" / "prompts").mkdir(parents=True)
    (tmp_path / "pipeline" / "prompts" / "compile.md").write_text(
        "COMPILE PROMPT", encoding="utf-8"
    )
    return tmp_path


def _seed_classified(path: Path, subtopic: str, body: str) -> None:
    fm = ClassifiedFrontmatter(
        source_file="sample_raw/a.md",
        source_date="2026-04-01",
        extracted_at=datetime(2026, 4, 24, 12, 0, 0),
        content_hash="h1",
        category="02-rule-stage",
        subtopic=subtopic,
    )
    write_frontmatter(path, fm, body)


def test_compile_writes_wiki_page_with_frontmatter_and_sources(workspace: Path) -> None:
    _seed_classified(
        workspace / "classified" / "02-rule-stage" / "a.md",
        "海女美術-ガチエリア",
        "右高台の制圧はリスクあり。",
    )

    clusters_path = workspace / "state" / "clusters.json"
    clusters_path.write_text(
        json.dumps(
            {"02-rule-stage/海女美術-ガチエリア": ["classified/02-rule-stage/a.md"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest_path = workspace / "state" / "ingest_manifest.json"
    Manifest().save(manifest_path)

    categories = [
        Category(id="02-rule-stage", label="ルール×ステージ", description="定石"),
    ]
    provider = FakeLLMProvider(responses=["## 海女美術 ガチエリア\n\n本文。"])
    stage_cfg = StageConfig(provider="fake", model="x", max_tokens=8192)

    compile_stage.run(
        provider=provider,
        stage_cfg=stage_cfg,
        categories=categories,
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        clusters_path=clusters_path,
        manifest_path=manifest_path,
        prompt_path=workspace / "pipeline" / "prompts" / "compile.md",
        source_urls={"sample_raw/a.md": "https://drive.google.com/file/d/AAA"},
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=workspace,
    )

    out = workspace / "wiki" / "02-rule-stage" / "海女美術-ガチエリア.md"
    assert out.exists()
    fm, body = read_frontmatter(out, WikiFrontmatter)
    assert fm.category == "02-rule-stage"
    assert fm.subtopic == "海女美術-ガチエリア"
    assert fm.sources == ["https://drive.google.com/file/d/AAA"]
    assert "## 海女美術 ガチエリア" in body
    assert "## 出典" in body
    assert "https://drive.google.com/file/d/AAA" in body


def test_compile_skips_unchanged_cluster(workspace: Path) -> None:
    _seed_classified(
        workspace / "classified" / "02-rule-stage" / "a.md",
        "海女美術-ガチエリア",
        "body",
    )
    clusters_path = workspace / "state" / "clusters.json"
    paths = ["classified/02-rule-stage/a.md"]
    clusters_path.write_text(
        json.dumps({"02-rule-stage/海女美術-ガチエリア": paths}, ensure_ascii=False),
        encoding="utf-8",
    )

    fingerprint = hashlib.sha256("\n".join(sorted(paths)).encode()).hexdigest()
    manifest_path = workspace / "state" / "ingest_manifest.json"
    manifest = Manifest(
        wiki={"wiki/02-rule-stage/海女美術-ガチエリア.md": {"cluster_fingerprint": fingerprint}}
    )
    manifest.save(manifest_path)

    provider = FakeLLMProvider(responses=[])  # will assert if called
    compile_stage.run(
        provider=provider,
        stage_cfg=StageConfig(provider="fake", model="x", max_tokens=1),
        categories=[Category(id="02-rule-stage", label="x", description="y")],
        classified_dir=workspace / "classified",
        wiki_dir=workspace / "wiki",
        clusters_path=clusters_path,
        manifest_path=manifest_path,
        prompt_path=workspace / "pipeline" / "prompts" / "compile.md",
        source_urls={},
        now=lambda: datetime(2026, 4, 24, 12, 0, 0),
        root=workspace,
    )

    assert provider.calls == []
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/stages/test_compile.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/stages/compile.py`**

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pipeline.config import Category, StageConfig
from pipeline.frontmatter_io import read_frontmatter, write_frontmatter
from pipeline.llm.base import LLMProvider
from pipeline.models import ClassifiedFrontmatter, WikiFrontmatter
from pipeline.state import Manifest


def _fingerprint(paths: list[str]) -> str:
    joined = "\n".join(sorted(paths))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _load_snippets(
    root: Path, paths: list[str]
) -> tuple[list[str], set[str]]:
    bodies: list[str] = []
    source_files: set[str] = set()
    for rel in paths:
        fm, body = read_frontmatter(root / rel, ClassifiedFrontmatter)
        assert fm is not None
        bodies.append(body.strip())
        source_files.add(fm.source_file)
    return bodies, source_files


def _build_user_prompt(category_label: str, subtopic: str, bodies: list[str]) -> str:
    numbered = "\n\n".join(f"{i + 1}. {b}" for i, b in enumerate(bodies))
    return (
        f"Category: {category_label}\n"
        f"Subtopic: {subtopic}\n\n"
        f"Snippets:\n{numbered}"
    )


def _with_sources(body: str, sources: list[str]) -> str:
    if not sources:
        return body.rstrip() + "\n"
    lines = ["", "## 出典", ""]
    for url in sources:
        lines.append(f"- {url}")
    lines.append("")
    return body.rstrip() + "\n\n" + "\n".join(lines)


def run(
    *,
    provider: LLMProvider,
    stage_cfg: StageConfig,
    categories: list[Category],
    classified_dir: Path,
    wiki_dir: Path,
    clusters_path: Path,
    manifest_path: Path,
    prompt_path: Path,
    source_urls: dict[str, str],
    now: Callable[[], datetime] = datetime.utcnow,
    root: Path | None = None,
) -> None:
    root = root or classified_dir.parent
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))
    manifest = Manifest.load(manifest_path)
    system_prompt = prompt_path.read_text(encoding="utf-8")
    label_by_id = {c.id: c.label for c in categories}

    for key, paths in clusters.items():
        category_id, subtopic = key.split("/", 1)
        wiki_rel = f"wiki/{category_id}/{subtopic}.md"
        fingerprint = _fingerprint(paths)

        prior = manifest.wiki.get(wiki_rel, {}).get("cluster_fingerprint")
        if prior == fingerprint:
            continue

        bodies, source_files = _load_snippets(root, paths)
        reply = provider.complete(
            system=system_prompt,
            user=_build_user_prompt(label_by_id[category_id], subtopic, bodies),
            model=stage_cfg.model,
            max_tokens=stage_cfg.max_tokens,
        )

        sources = sorted(source_urls[s] for s in source_files if s in source_urls)
        final_body = _with_sources(reply, sources)
        updated_at = now()

        fm = WikiFrontmatter(
            category=category_id,
            subtopic=subtopic,
            sources=sources,
            updated_at=updated_at,
        )
        out = wiki_dir / category_id / f"{subtopic}.md"
        write_frontmatter(out, fm, final_body)

        manifest.wiki[wiki_rel] = {"cluster_fingerprint": fingerprint}

    manifest.save(manifest_path)
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/stages/test_compile.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/stages/compile.py tests/stages/test_compile.py
git commit -m "feat(stages): add Compile stage generating wiki MD per subtopic cluster"
```

---

## Task 15: Stage 5 — Diff & Commit

**Files:**
- Create: `pipeline/stages/diff_commit.py`
- Create: `tests/stages/test_diff_commit.py`

- [ ] **Step 1: Write the failing test**

`tests/stages/test_diff_commit.py`:
```python
import subprocess
from pathlib import Path

import pytest

from pipeline.stages import diff_commit


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "initial.md").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_commits_changes_when_wiki_modified(git_repo: Path) -> None:
    (git_repo / "wiki" / "new.md").write_text("hello", encoding="utf-8")

    result = diff_commit.run(repo_root=git_repo, wiki_dir=git_repo / "wiki")

    assert result is True
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=git_repo, check=True, capture_output=True, text=True
    )
    assert "wiki:" in log.stdout


def test_noop_when_no_changes(git_repo: Path) -> None:
    result = diff_commit.run(repo_root=git_repo, wiki_dir=git_repo / "wiki")
    assert result is False
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/stages/test_diff_commit.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pipeline/stages/diff_commit.py`**

```python
from __future__ import annotations

import subprocess
from pathlib import Path


def _has_changes(repo_root: Path, rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", rel_path],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def run(*, repo_root: Path, wiki_dir: Path, message: str = "wiki: regenerate pages") -> bool:
    rel = wiki_dir.relative_to(repo_root)
    if not _has_changes(repo_root, str(rel)):
        return False
    subprocess.run(["git", "add", "--", str(rel)], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True)
    return True
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/stages/test_diff_commit.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/stages/diff_commit.py tests/stages/test_diff_commit.py
git commit -m "feat(stages): add Diff & Commit stage that auto-commits wiki changes"
```

---

## Task 16: Main CLI entrypoint

**Files:**
- Create: `pipeline/main.py`
- Create: `tests/test_main_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_main_cli.py`:
```python
from pathlib import Path

import pytest

from pipeline import main


def test_parse_args_single_stage() -> None:
    args = main.parse_args(["--stage", "ingest"])
    assert args.stage == "ingest"
    assert args.all is False


def test_parse_args_all() -> None:
    args = main.parse_args(["--all"])
    assert args.all is True


def test_parse_args_requires_one(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        main.parse_args([])


def test_parse_args_rejects_unknown_stage() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--stage", "bogus"])
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run pytest tests/test_main_cli.py -v`
Expected: FAIL — `ImportError` for `main`.

- [ ] **Step 3: Implement `pipeline/main.py`**

```python
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.config import load_categories, load_pipeline
from pipeline.llm.base import get_provider
from pipeline.stages import classify, cluster, compile as compile_stage, diff_commit, ingest

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
            source_urls={},  # MVP: empty; Drive integration populates later
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
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run pytest tests/test_main_cli.py -v`
Expected: 4 passed.

- [ ] **Step 5: Verify CLI help works**

Run: `uv run python -m pipeline.main --help`
Expected: argparse help output listing `--stage` and `--all`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/main.py tests/test_main_cli.py
git commit -m "feat(cli): add main entrypoint dispatching to individual stages"
```

---

## Task 17: End-to-end smoke test with fake LLM

**Files:**
- Create: `tests/test_end_to_end.py`

- [ ] **Step 1: Write the test**

`tests/test_end_to_end.py`:
```python
import json
import subprocess
from datetime import datetime
from pathlib import Path

from pipeline.config import Category, StageConfig
from pipeline.llm.fake import FakeLLMProvider
from pipeline.stages import classify, cluster, compile as compile_stage, diff_commit, ingest


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True)


def test_pipeline_end_to_end_with_fake_llm(tmp_path: Path) -> None:
    root = tmp_path
    for sub in ["sample_raw", "snippets", "classified", "wiki", "state", "pipeline/prompts"]:
        (root / sub).mkdir(parents=True, exist_ok=True)

    (root / "pipeline" / "prompts" / "ingest.md").write_text("INGEST", encoding="utf-8")
    (root / "pipeline" / "prompts" / "classify.md").write_text("CLASSIFY", encoding="utf-8")
    (root / "pipeline" / "prompts" / "compile.md").write_text("COMPILE", encoding="utf-8")

    (root / "sample_raw" / "2026-04-01-notes.md").write_text(
        "右高台の話など。", encoding="utf-8"
    )
    _init_repo(root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)

    categories = [
        Category(id="02-rule-stage", label="ルール×ステージ", description="定石"),
    ]

    # Ingest returns 1 snippet
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
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests pass (including the new e2e test). Count should be 27+.

- [ ] **Step 3: Commit**

```bash
git add tests/test_end_to_end.py
git commit -m "test: add end-to-end pipeline test with fake LLM"
```

---

## Task 18: Final verification and README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run ruff check and full test suite**

Run: `uv run ruff check .`
Expected: "All checks passed!" (fix any reported issues before continuing).

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 2: Write `README.md`**

```markdown
# splatoon3-wiki

LLM-generated Splatoon 3 knowledge wiki. Sub-project #1: generation pipeline.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Anthropic API key (Claude) and Google Gen AI API key (Gemini)

## Setup

```bash
uv sync --extra dev
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and GEMINI_API_KEY
```

## Running the pipeline

Run a single stage:
```bash
uv run python -m pipeline.main --stage ingest
uv run python -m pipeline.main --stage classify
uv run python -m pipeline.main --stage cluster
uv run python -m pipeline.main --stage compile
uv run python -m pipeline.main --stage diff
```

Or all at once:
```bash
uv run python -m pipeline.main --all
```

## Testing

```bash
uv run pytest
uv run ruff check .
```

## Design

See [`docs/superpowers/specs/2026-04-23-llm-wiki-pipeline-design.md`](docs/superpowers/specs/2026-04-23-llm-wiki-pipeline-design.md).
```

- [ ] **Step 3: Smoke test via CLI**

Set the `fake` provider for a dry run. Temporarily edit `config/pipeline.yaml`:
```yaml
stages:
  ingest:
    provider: fake
    model: fake
    max_tokens: 1
  classify:
    provider: fake
    model: fake
    max_tokens: 1
  compile:
    provider: fake
    model: fake
    max_tokens: 1
```

Run: `uv run python -m pipeline.main --stage cluster`
Expected: runs without error (cluster is the only stage that does not call the LLM). Creates `state/clusters.json`.

Revert `config/pipeline.yaml` to the original provider settings.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and run instructions"
```

- [ ] **Step 5: Push to remote**

```bash
git push -u origin main
```

---

## Completion checklist

- [ ] All 18 tasks committed on `main`
- [ ] `uv run pytest` — all passing
- [ ] `uv run ruff check .` — all passing
- [ ] README and design spec are in sync
- [ ] Sample raw MD files generate non-empty wiki pages when pipeline runs with real API keys (manual smoke; not gated)
