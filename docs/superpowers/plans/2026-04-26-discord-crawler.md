# Discord Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a weekly Discord crawler that fetches messages from configured servers/channels into local Markdown files, packaged as a one-shot Docker container.

**Architecture:** New top-level `crawler/` Python module split by responsibility (`config`, `week`, `models`, `client`, `fetch`, `writer`, `main`). Discord-library knowledge is isolated to `client.py`; everything downstream operates on plain `Message` pydantic models. Tests use a `FakeDiscordClient` so the suite never hits real Discord. Output goes to `raw_cache/discord/<server>/<channel>/<YYYY-Wnn>.md` (already in `.gitignore`).

**Tech Stack:** Python 3.12, discord.py (new optional dep), pydantic v2, PyYAML, asyncio, argparse. Docker base `python:3.12-slim`. Test runner pytest + pytest-asyncio (new).

**Spec reference:** `docs/superpowers/specs/2026-04-26-discord-crawler-design.md`

---

## File Structure

**New files:**

- `crawler/__init__.py` — empty package marker
- `crawler/__main__.py` — enables `python -m crawler`
- `crawler/models.py` — `Author`, `Attachment`, `Reaction`, `Message` pydantic models
- `crawler/week.py` — `iso_week_range_jst()`, `parse_week_id()`
- `crawler/config.py` — `ChannelConfig`, `ServerConfig`, `CrawlConfig`, `load_crawl_config()`
- `crawler/writer.py` — `format_message_block()`, `channel_week_path()`, `write_week_file()`
- `crawler/client.py` — `DiscordClientProtocol`, real `DiscordClient`, helper `convert_discord_message()`
- `crawler/fetch.py` — `fetch_channel_week()`
- `crawler/main.py` — `parse_args()`, `run_crawl()`, `main()`
- `tests/crawler/__init__.py`
- `tests/crawler/conftest.py` — `FakeDiscordClient` (test-only fake implementing the protocol)
- `tests/crawler/test_models.py`
- `tests/crawler/test_week.py`
- `tests/crawler/test_config.py`
- `tests/crawler/test_writer.py`
- `tests/crawler/test_fetch.py`
- `tests/crawler/test_main_cli.py`
- `tests/crawler/test_e2e_fake.py`
- `config/discord.yaml.example` — sample config tracked in git
- `docker/crawler/Dockerfile`
- `docker/crawler/crontab.example`

**Modified files:**

- `pyproject.toml` — add `[project.optional-dependencies] crawler = ["discord.py>=2.4.0"]` and `pytest-asyncio>=0.24.0` to dev extras
- `.env.example` — add `DISCORD_BOT_TOKEN=` line (if file exists; create if not)

**Each file's responsibility:**

- `models.py`: data shape only — no IO, no Discord dependency.
- `week.py`: pure functions over `datetime`, no IO.
- `config.py`: YAML → pydantic. Validation only.
- `writer.py`: pydantic `Message` list → Markdown bytes on disk. Sync, no Discord dep.
- `client.py`: only file that imports `discord`. Defines `DiscordClientProtocol` (the abstract contract used by `fetch.py` and tests) and the concrete `DiscordClient` adapter.
- `fetch.py`: orchestrates one channel × one week using a `DiscordClientProtocol` (Discord library is invisible here).
- `main.py`: CLI entry, asyncio boundary, orchestration loop, summary logging.
- `tests/crawler/conftest.py`: home of `FakeDiscordClient` so every test file can import it.

---

## Task 1: Scaffolding (deps, dirs, sample config)

**Files:**
- Modify: `pyproject.toml`
- Create: `crawler/__init__.py`
- Create: `crawler/__main__.py`
- Create: `tests/crawler/__init__.py`
- Create: `config/discord.yaml.example`

This task adds the dependency, creates empty package skeletons, and a tracked example config. No production logic yet.

- [ ] **Step 1: Add discord.py and pytest-asyncio to pyproject.toml**

In `pyproject.toml`, replace the `[project.optional-dependencies]` block with:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.6.0",
]
crawler = [
    "discord.py>=2.4.0",
]
```

Also append to `[tool.pytest.ini_options]`:

```toml
asyncio_mode = "auto"
```

so the full block becomes:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
asyncio_mode = "auto"
```

- [ ] **Step 2: Install new dev deps and crawler extra**

Run: `uv sync --extra dev --extra crawler`
Expected: success. `discord.py` and `pytest-asyncio` appear in `uv.lock`.

- [ ] **Step 3: Create empty package marker files**

Create `crawler/__init__.py` with a single line:

```python
"""Discord crawler — weekly message fetcher for the wiki pipeline."""
```

Create `crawler/__main__.py`:

```python
from crawler.main import main

if __name__ == "__main__":
    main()
```

Create `tests/crawler/__init__.py` as an empty file.

- [ ] **Step 4: Create `config/discord.yaml.example`**

Write to `config/discord.yaml.example`:

```yaml
# Copy to config/discord.yaml and fill in real IDs.
# Server / channel IDs MUST be quoted strings (Discord snowflakes are 64-bit).

output_dir: raw_cache/discord
timezone: Asia/Tokyo

servers:
  - id: "123456789012345678"
    name: "Splatoon道場"
    channels:
      - id: "234567890123456789"
        name: "戦術談義"
      - id: "234567890123456790"
        name: "海女美術"
```

- [ ] **Step 5: Add `DISCORD_BOT_TOKEN=` to .env.example**

If `.env.example` exists, append:

```
DISCORD_BOT_TOKEN=
```

If not, create it with the existing pipeline keys plus the new one. Check `.env.example` first to see what is there.

- [ ] **Step 6: Verify imports work**

Run: `uv run python -c "import crawler; print('ok')"`
Expected: prints `ok`.

Run: `uv run python -c "import discord; print(discord.__version__)"`
Expected: prints a version `>= 2.4.0`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock crawler/__init__.py crawler/__main__.py tests/crawler/__init__.py config/discord.yaml.example .env.example
git commit -m "chore(crawler): scaffold module, add discord.py + pytest-asyncio deps"
```

---

## Task 2: Pydantic models

**Files:**
- Create: `crawler/models.py`
- Create: `tests/crawler/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `tests/crawler/test_models.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from crawler.models import Attachment, Author, Message, Reaction


def test_message_minimal_fields() -> None:
    msg = Message(
        id="1234",
        author=Author(id="111", username="alice", display_name="Alice"),
        timestamp=datetime(2026, 4, 22, 14, 32, 11, tzinfo=timezone.utc),
        content="hello",
    )
    assert msg.id == "1234"
    assert msg.author.username == "alice"
    assert msg.edited_at is None
    assert msg.reply_to is None
    assert msg.thread_id is None
    assert msg.attachments == []
    assert msg.embeds == []
    assert msg.reactions == []


def test_message_full_fields() -> None:
    msg = Message(
        id="1",
        author=Author(id="2", username="u", display_name="d"),
        timestamp=datetime(2026, 4, 22, tzinfo=timezone.utc),
        content="body",
        edited_at=datetime(2026, 4, 22, 1, tzinfo=timezone.utc),
        reply_to="999",
        thread_id="888",
        attachments=[Attachment(url="https://cdn.x/a.png")],
        embeds=["https://yt.example/v"],
        reactions=[Reaction(emoji="👍", count=3)],
    )
    assert msg.attachments[0].url == "https://cdn.x/a.png"
    assert msg.reactions[0].count == 3


def test_reaction_count_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Reaction(emoji="👍", count=0)


def test_message_id_must_be_nonempty() -> None:
    with pytest.raises(ValidationError):
        Message(
            id="",
            author=Author(id="2", username="u", display_name="d"),
            timestamp=datetime(2026, 4, 22, tzinfo=timezone.utc),
            content="body",
        )
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/crawler/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.models'`.

- [ ] **Step 3: Implement `crawler/models.py`**

Create `crawler/models.py`:

```python
from datetime import datetime

from pydantic import BaseModel, Field


class Author(BaseModel):
    id: str = Field(min_length=1)
    username: str = Field(min_length=1)
    display_name: str = Field(min_length=1)


class Attachment(BaseModel):
    url: str = Field(min_length=1)


class Reaction(BaseModel):
    emoji: str = Field(min_length=1)
    count: int = Field(gt=0)


class Message(BaseModel):
    id: str = Field(min_length=1)
    author: Author
    timestamp: datetime
    content: str
    edited_at: datetime | None = None
    reply_to: str | None = None
    thread_id: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    embeds: list[str] = Field(default_factory=list)
    reactions: list[Reaction] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `uv run pytest tests/crawler/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check crawler/models.py tests/crawler/test_models.py`
Run: `uv run ruff format --check crawler/models.py tests/crawler/test_models.py`
Auto-fix with `uv run ruff format ...` if needed.

- [ ] **Step 6: Commit**

```bash
git add crawler/models.py tests/crawler/test_models.py
git commit -m "feat(crawler): add Message / Author / Reaction / Attachment models"
```

---

## Task 3: ISO week range (JST)

**Files:**
- Create: `crawler/week.py`
- Create: `tests/crawler/test_week.py`

- [ ] **Step 1: Write failing tests**

Create `tests/crawler/test_week.py`:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from crawler.week import iso_week_range_jst, parse_week_id

JST = ZoneInfo("Asia/Tokyo")


def test_returns_previous_iso_week_for_midweek_jst() -> None:
    # 2026-04-26 is a Sunday in JST and falls in 2026-W17 (Mon 4/20 ~ Sun 4/26).
    # The function returns the ISO week strictly preceding `now`, so 2026-W16.
    now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=JST)
    week_id, start, end = iso_week_range_jst(now)
    assert week_id == "2026-W16"
    assert start == datetime(2026, 4, 13, 0, 0, 0, tzinfo=JST)
    assert end == datetime(2026, 4, 20, 0, 0, 0, tzinfo=JST)


def test_handles_monday_start_of_week() -> None:
    # Monday 2026-04-27 00:30 JST: previous week = W17 (4/20 ~ 4/26).
    now = datetime(2026, 4, 27, 0, 30, 0, tzinfo=JST)
    week_id, start, end = iso_week_range_jst(now)
    assert week_id == "2026-W17"
    assert start == datetime(2026, 4, 20, 0, 0, 0, tzinfo=JST)
    assert end == datetime(2026, 4, 27, 0, 0, 0, tzinfo=JST)


def test_handles_year_boundary() -> None:
    # Mon 2026-01-05 09:00 JST → previous week = 2025-W53 (since 2025 has 53 ISO weeks)
    now = datetime(2026, 1, 5, 9, 0, 0, tzinfo=JST)
    week_id, start, end = iso_week_range_jst(now)
    # Verify week_id format and that start/end are 7 days apart and Mondays.
    assert "-W" in week_id
    assert (end - start).days == 7
    assert start.weekday() == 0  # Monday
    assert end.weekday() == 0


def test_converts_utc_now_to_jst_before_computing() -> None:
    # 2026-04-27 00:00 UTC = 2026-04-27 09:00 JST (Monday morning).
    # Previous week = W17.
    now_utc = datetime(2026, 4, 27, 0, 0, 0, tzinfo=timezone.utc)
    week_id, _, _ = iso_week_range_jst(now_utc)
    assert week_id == "2026-W17"


def test_naive_datetime_raises() -> None:
    with pytest.raises(ValueError):
        iso_week_range_jst(datetime(2026, 4, 26, 12, 0, 0))


def test_parse_week_id_roundtrip() -> None:
    week_id, start, end = parse_week_id("2026-W17")
    assert week_id == "2026-W17"
    assert start == datetime(2026, 4, 20, 0, 0, 0, tzinfo=JST)
    assert end == datetime(2026, 4, 27, 0, 0, 0, tzinfo=JST)


def test_parse_week_id_invalid_format() -> None:
    with pytest.raises(ValueError):
        parse_week_id("2026-17")
    with pytest.raises(ValueError):
        parse_week_id("not-a-week")
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/crawler/test_week.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.week'`.

- [ ] **Step 3: Implement `crawler/week.py`**

Create `crawler/week.py`:

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def iso_week_range_jst(now: datetime) -> tuple[str, datetime, datetime]:
    """Return (week_id, start, end) for the ISO week strictly preceding `now`.

    All datetimes are JST-aware. `start` is Monday 00:00, `end` is the next
    Monday 00:00 (exclusive). `week_id` is "YYYY-Www" using ISO 8601 numbering.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now_jst = now.astimezone(JST)
    days_since_monday = now_jst.weekday()  # Monday = 0
    this_monday = (now_jst - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    prev_monday = this_monday - timedelta(days=7)
    iso_year, iso_week, _ = prev_monday.isocalendar()
    week_id = f"{iso_year}-W{iso_week:02d}"
    return week_id, prev_monday, this_monday


def parse_week_id(week_id: str) -> tuple[str, datetime, datetime]:
    """Parse 'YYYY-Wnn' into (week_id, start, end) JST-aware.

    `start` is Monday 00:00 JST of that ISO week; `end` is the next Monday.
    """
    parts = week_id.split("-W")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"invalid week_id: {week_id!r}")
    year, week = int(parts[0]), int(parts[1])
    start_naive = datetime.fromisocalendar(year, week, 1)  # Monday
    start = start_naive.replace(tzinfo=JST)
    end = start + timedelta(days=7)
    return week_id, start, end
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `uv run pytest tests/crawler/test_week.py -v`
Expected: 7 passed.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check crawler/week.py tests/crawler/test_week.py`
Run: `uv run ruff format --check crawler/week.py tests/crawler/test_week.py`

- [ ] **Step 6: Commit**

```bash
git add crawler/week.py tests/crawler/test_week.py
git commit -m "feat(crawler): add ISO week range helper with JST boundaries"
```

---

## Task 4: Config loader

**Files:**
- Create: `crawler/config.py`
- Create: `tests/crawler/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/crawler/test_config.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from crawler.config import CrawlConfig, load_crawl_config


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_load_minimal_valid_config(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers:
  - id: "111"
    name: "ServerA"
    channels:
      - id: "222"
        name: "ChannelA"
""".strip(),
    )
    cfg = load_crawl_config(p)
    assert cfg.output_dir == Path("raw_cache/discord")
    assert cfg.timezone == "Asia/Tokyo"
    assert len(cfg.servers) == 1
    assert cfg.servers[0].channels[0].name == "ChannelA"


def test_load_multiple_servers_and_channels(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers:
  - id: "111"
    name: "A"
    channels:
      - id: "1"
        name: "ch1"
      - id: "2"
        name: "ch2"
  - id: "222"
    name: "B"
    channels:
      - id: "3"
        name: "ch3"
""".strip(),
    )
    cfg = load_crawl_config(p)
    assert len(cfg.servers) == 2
    assert sum(len(s.channels) for s in cfg.servers) == 3


def test_missing_servers_field_raises(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
""".strip(),
    )
    with pytest.raises(ValidationError):
        load_crawl_config(p)


def test_empty_servers_list_raises(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers: []
""".strip(),
    )
    with pytest.raises(ValidationError):
        load_crawl_config(p)


def test_numeric_id_in_yaml_raises(tmp_path: Path) -> None:
    # Snowflakes must be quoted strings; bare numbers risk precision loss
    # and are explicitly disallowed.
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers:
  - id: 123456789012345678
    name: "S"
    channels:
      - id: "1"
        name: "c"
""".strip(),
    )
    with pytest.raises(ValidationError):
        load_crawl_config(p)


def test_default_timezone_is_jst(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
servers:
  - id: "111"
    name: "S"
    channels:
      - id: "1"
        name: "c"
""".strip(),
    )
    cfg = load_crawl_config(p)
    assert cfg.timezone == "Asia/Tokyo"


def test_crawl_config_direct_construction() -> None:
    cfg = CrawlConfig.model_validate(
        {
            "output_dir": "raw_cache/discord",
            "servers": [
                {"id": "1", "name": "S", "channels": [{"id": "2", "name": "c"}]},
            ],
        }
    )
    assert cfg.timezone == "Asia/Tokyo"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/crawler/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `crawler/config.py`**

Create `crawler/config.py`:

```python
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, StrictStr


class ChannelConfig(BaseModel):
    id: StrictStr = Field(min_length=1)
    name: StrictStr = Field(min_length=1)


class ServerConfig(BaseModel):
    id: StrictStr = Field(min_length=1)
    name: StrictStr = Field(min_length=1)
    channels: list[ChannelConfig] = Field(min_length=1)


class CrawlConfig(BaseModel):
    output_dir: Path
    timezone: StrictStr = "Asia/Tokyo"
    servers: list[ServerConfig] = Field(min_length=1)


def load_crawl_config(path: Path) -> CrawlConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CrawlConfig.model_validate(data)
```

`StrictStr` is what makes `test_numeric_id_in_yaml_raises` pass — a bare number in YAML loads as `int`, which `StrictStr` rejects.

- [ ] **Step 4: Run tests and verify they pass**

Run: `uv run pytest tests/crawler/test_config.py -v`
Expected: 7 passed.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check crawler/config.py tests/crawler/test_config.py`
Run: `uv run ruff format --check crawler/config.py tests/crawler/test_config.py`

- [ ] **Step 6: Commit**

```bash
git add crawler/config.py tests/crawler/test_config.py
git commit -m "feat(crawler): add CrawlConfig loader with strict snowflake validation"
```

---

## Task 5: Markdown writer

**Files:**
- Create: `crawler/writer.py`
- Create: `tests/crawler/test_writer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/crawler/test_writer.py`:

```python
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from crawler.models import Attachment, Author, Message, Reaction
from crawler.writer import channel_week_path, format_message_block, write_week_file

JST = ZoneInfo("Asia/Tokyo")


def _msg(**overrides) -> Message:
    base = dict(
        id="1",
        author=Author(id="100", username="alice", display_name="Alice"),
        timestamp=datetime(2026, 4, 22, 14, 32, 11, tzinfo=JST),
        content="hello world",
    )
    base.update(overrides)
    return Message(**base)


def test_channel_week_path_slugifies_unsafe_chars(tmp_path: Path) -> None:
    out = tmp_path / "raw_cache" / "discord"
    p = channel_week_path(out, "Splatoon道場", "戦/術", "2026-W17")
    assert p == out / "Splatoon道場" / "戦_術" / "2026-W17.md"


def test_format_message_block_minimal() -> None:
    block = format_message_block(_msg())
    assert block.startswith("## msg-1\n")
    assert '- author_id: "100"' in block
    assert '- author_username: "alice"' in block
    assert '- author_display_name: "Alice"' in block
    assert '- timestamp: "2026-04-22T14:32:11+09:00"' in block
    assert "edited_at" not in block
    assert "reply_to" not in block
    assert "thread_id" not in block
    assert "attachments" not in block
    assert "embeds" not in block
    assert "reactions" not in block
    assert block.rstrip().endswith("hello world")


def test_format_message_block_full() -> None:
    block = format_message_block(
        _msg(
            edited_at=datetime(2026, 4, 22, 14, 35, tzinfo=JST),
            reply_to="999",
            thread_id="888",
            attachments=[Attachment(url="https://cdn.x/a.png")],
            embeds=["https://yt.example/v"],
            reactions=[Reaction(emoji="👍", count=5), Reaction(emoji="🎯", count=2)],
            content="multi\nline\nbody",
        )
    )
    assert '- edited_at: "2026-04-22T14:35:00+09:00"' in block
    assert '- reply_to: "999"' in block
    assert '- thread_id: "888"' in block
    assert "- attachments:" in block
    assert '  - "https://cdn.x/a.png"' in block
    assert "- embeds:" in block
    assert '  - "https://yt.example/v"' in block
    assert "- reactions:" in block
    assert '  - "👍": 5' in block
    assert '  - "🎯": 2' in block
    assert "multi\nline\nbody" in block


def test_write_week_file_creates_file_with_frontmatter(tmp_path: Path) -> None:
    out = tmp_path / "raw_cache" / "discord"
    path = channel_week_path(out, "S", "C", "2026-W17")
    written = write_week_file(
        path=path,
        server_id="111",
        server_name="S",
        channel_id="222",
        channel_name="C",
        week_id="2026-W17",
        week_start=datetime(2026, 4, 20, tzinfo=JST),
        week_end=datetime(2026, 4, 27, tzinfo=JST),
        fetched_at=datetime(2026, 4, 27, 9, tzinfo=JST),
        messages=[_msg()],
        force=False,
    )
    assert written is True
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert 'server_id: "111"' in text
    assert 'channel_name: C' in text or 'channel_name: "C"' in text
    assert "week: 2026-W17" in text or 'week: "2026-W17"' in text
    assert "message_count: 1" in text
    assert "## msg-1" in text


def test_write_week_file_skips_when_existing_and_not_forced(tmp_path: Path) -> None:
    out = tmp_path / "raw_cache" / "discord"
    path = channel_week_path(out, "S", "C", "2026-W17")
    path.parent.mkdir(parents=True)
    path.write_text("existing", encoding="utf-8")

    written = write_week_file(
        path=path,
        server_id="111",
        server_name="S",
        channel_id="222",
        channel_name="C",
        week_id="2026-W17",
        week_start=datetime(2026, 4, 20, tzinfo=JST),
        week_end=datetime(2026, 4, 27, tzinfo=JST),
        fetched_at=datetime(2026, 4, 27, 9, tzinfo=JST),
        messages=[_msg()],
        force=False,
    )
    assert written is False
    assert path.read_text(encoding="utf-8") == "existing"


def test_write_week_file_overwrites_when_forced(tmp_path: Path) -> None:
    out = tmp_path / "raw_cache" / "discord"
    path = channel_week_path(out, "S", "C", "2026-W17")
    path.parent.mkdir(parents=True)
    path.write_text("existing", encoding="utf-8")

    written = write_week_file(
        path=path,
        server_id="111",
        server_name="S",
        channel_id="222",
        channel_name="C",
        week_id="2026-W17",
        week_start=datetime(2026, 4, 20, tzinfo=JST),
        week_end=datetime(2026, 4, 27, tzinfo=JST),
        fetched_at=datetime(2026, 4, 27, 9, tzinfo=JST),
        messages=[_msg()],
        force=True,
    )
    assert written is True
    text = path.read_text(encoding="utf-8")
    assert "existing" not in text
    assert "## msg-1" in text


def test_write_week_file_handles_zero_messages(tmp_path: Path) -> None:
    out = tmp_path / "raw_cache" / "discord"
    path = channel_week_path(out, "S", "C", "2026-W18")
    written = write_week_file(
        path=path,
        server_id="111",
        server_name="S",
        channel_id="222",
        channel_name="C",
        week_id="2026-W18",
        week_start=datetime(2026, 4, 27, tzinfo=JST),
        week_end=datetime(2026, 5, 4, tzinfo=JST),
        fetched_at=datetime(2026, 5, 4, 9, tzinfo=JST),
        messages=[],
        force=False,
    )
    assert written is True
    text = path.read_text(encoding="utf-8")
    assert "message_count: 0" in text
    assert "## msg-" not in text


def test_write_week_file_no_partial_left_after_success(tmp_path: Path) -> None:
    out = tmp_path / "raw_cache" / "discord"
    path = channel_week_path(out, "S", "C", "2026-W17")
    write_week_file(
        path=path,
        server_id="111",
        server_name="S",
        channel_id="222",
        channel_name="C",
        week_id="2026-W17",
        week_start=datetime(2026, 4, 20, tzinfo=JST),
        week_end=datetime(2026, 4, 27, tzinfo=JST),
        fetched_at=datetime(2026, 4, 27, 9, tzinfo=JST),
        messages=[_msg()],
    )
    partial = path.with_suffix(path.suffix + ".partial")
    assert not partial.exists()
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/crawler/test_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.writer'`.

- [ ] **Step 3: Implement `crawler/writer.py`**

Create `crawler/writer.py`:

```python
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import yaml

from crawler.models import Message

_PATH_UNSAFE = ("/", "\\")


def _slugify(name: str) -> str:
    out = name
    for ch in _PATH_UNSAFE:
        out = out.replace(ch, "_")
    return out


def channel_week_path(
    out_dir: Path, server_name: str, channel_name: str, week_id: str
) -> Path:
    return out_dir / _slugify(server_name) / _slugify(channel_name) / f"{week_id}.md"


def format_message_block(msg: Message) -> str:
    lines: list[str] = [f"## msg-{msg.id}", ""]
    lines.append(f'- author_id: "{msg.author.id}"')
    lines.append(f'- author_username: "{msg.author.username}"')
    lines.append(f'- author_display_name: "{msg.author.display_name}"')
    lines.append(f'- timestamp: "{msg.timestamp.isoformat()}"')
    if msg.edited_at is not None:
        lines.append(f'- edited_at: "{msg.edited_at.isoformat()}"')
    if msg.reply_to is not None:
        lines.append(f'- reply_to: "{msg.reply_to}"')
    if msg.thread_id is not None:
        lines.append(f'- thread_id: "{msg.thread_id}"')
    if msg.attachments:
        lines.append("- attachments:")
        for a in msg.attachments:
            lines.append(f'  - "{a.url}"')
    if msg.embeds:
        lines.append("- embeds:")
        for u in msg.embeds:
            lines.append(f'  - "{u}"')
    if msg.reactions:
        lines.append("- reactions:")
        for r in msg.reactions:
            lines.append(f'  - "{r.emoji}": {r.count}')
    lines.append("")
    lines.append(msg.content)
    return "\n".join(lines)


def write_week_file(
    *,
    path: Path,
    server_id: str,
    server_name: str,
    channel_id: str,
    channel_name: str,
    week_id: str,
    week_start: datetime,
    week_end: datetime,
    fetched_at: datetime,
    messages: list[Message],
    force: bool = False,
) -> bool:
    """Write a week file. Returns True if written, False if skipped."""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "server_id": server_id,
        "server_name": server_name,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "week": week_id,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "fetched_at": fetched_at.isoformat(),
        "message_count": len(messages),
    }
    fm_yaml = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    blocks = [format_message_block(m) for m in messages]
    body = "\n\n---\n\n".join(blocks)
    content = f"---\n{fm_yaml}---\n\n{body}\n" if blocks else f"---\n{fm_yaml}---\n"

    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(content, encoding="utf-8")
    os.replace(partial, path)
    return True
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `uv run pytest tests/crawler/test_writer.py -v`
Expected: 8 passed.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check crawler/writer.py tests/crawler/test_writer.py`
Run: `uv run ruff format --check crawler/writer.py tests/crawler/test_writer.py`

- [ ] **Step 6: Commit**

```bash
git add crawler/writer.py tests/crawler/test_writer.py
git commit -m "feat(crawler): add Markdown writer with atomic write and skip/force"
```

---

## Task 6: Discord client adapter (Protocol + real impl + Fake fixture)

**Files:**
- Create: `crawler/client.py`
- Create: `tests/crawler/conftest.py` (FakeDiscordClient)

This task isolates discord.py behind a `DiscordClientProtocol`. The real `DiscordClient` is a thin adapter — its correctness is verified manually against a live Discord server (Task 10). The `FakeDiscordClient` lives in `tests/crawler/conftest.py` so all later test files can import it.

- [ ] **Step 1: Create `tests/crawler/conftest.py` with FakeDiscordClient**

Create `tests/crawler/conftest.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime

import pytest

from crawler.models import Message


@dataclass
class FakeChannelData:
    """Stored fixture data for one channel within FakeDiscordClient."""

    messages: list[Message] = field(default_factory=list)
    thread_messages: dict[str, list[Message]] = field(default_factory=dict)


class FakeDiscordClient:
    """In-memory implementation of DiscordClientProtocol for tests.

    Populate `channels` and `threads` via the constructor. The Fake exposes
    the same async API as the real adapter and filters by [after, before).
    """

    def __init__(
        self,
        channels: dict[str, FakeChannelData] | None = None,
    ) -> None:
        self.channels: dict[str, FakeChannelData] = channels or {}
        self.fetch_calls: list[tuple[str, datetime, datetime]] = []
        self.thread_calls: list[tuple[str, datetime, datetime]] = []
        self.active_thread_calls: list[str] = []

    async def __aenter__(self) -> "FakeDiscordClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def fetch_channel_messages(
        self, channel_id: str, after: datetime, before: datetime
    ) -> AsyncIterator[Message]:
        self.fetch_calls.append((channel_id, after, before))
        data = self.channels.get(channel_id, FakeChannelData())
        for m in data.messages:
            if after <= m.timestamp < before:
                yield m

    async def fetch_active_thread_ids(self, channel_id: str) -> list[str]:
        self.active_thread_calls.append(channel_id)
        return list(self.channels.get(channel_id, FakeChannelData()).thread_messages.keys())

    async def fetch_thread_messages(
        self, thread_id: str, after: datetime, before: datetime
    ) -> AsyncIterator[Message]:
        self.thread_calls.append((thread_id, after, before))
        for data in self.channels.values():
            if thread_id in data.thread_messages:
                for m in data.thread_messages[thread_id]:
                    if after <= m.timestamp < before:
                        yield m
                return


@pytest.fixture
def fake_client() -> FakeDiscordClient:
    return FakeDiscordClient()
```

- [ ] **Step 2: Implement `crawler/client.py`**

Create `crawler/client.py`:

```python
from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol

from crawler.models import Attachment, Author, Message, Reaction


class DiscordClientProtocol(Protocol):
    async def __aenter__(self) -> "DiscordClientProtocol": ...
    async def __aexit__(self, *args: object) -> None: ...

    def fetch_channel_messages(
        self, channel_id: str, after: datetime, before: datetime
    ) -> AsyncIterator[Message]: ...

    async def fetch_active_thread_ids(self, channel_id: str) -> list[str]: ...

    def fetch_thread_messages(
        self, thread_id: str, after: datetime, before: datetime
    ) -> AsyncIterator[Message]: ...


def convert_discord_message(raw: object, *, thread_id: str | None = None) -> Message:
    """Convert a discord.Message into our Message model.

    `raw` is typed as object because discord.py types can't be imported at
    module top level without the optional dep. Field access is duck-typed.
    """
    embeds: list[str] = []
    for e in getattr(raw, "embeds", []):
        url = getattr(e, "url", None)
        if url:
            embeds.append(url)

    attachments = [Attachment(url=a.url) for a in getattr(raw, "attachments", [])]

    reactions: list[Reaction] = []
    for r in getattr(raw, "reactions", []):
        emoji_obj = getattr(r, "emoji", None)
        emoji = str(emoji_obj) if emoji_obj is not None else "?"
        count = int(getattr(r, "count", 0))
        if count > 0:
            reactions.append(Reaction(emoji=emoji, count=count))

    author_obj = raw.author  # type: ignore[attr-defined]
    author = Author(
        id=str(author_obj.id),
        username=author_obj.name,
        display_name=getattr(author_obj, "display_name", author_obj.name),
    )

    reference = getattr(raw, "reference", None)
    reply_to = (
        str(reference.message_id)
        if reference is not None and getattr(reference, "message_id", None)
        else None
    )

    return Message(
        id=str(raw.id),  # type: ignore[attr-defined]
        author=author,
        timestamp=raw.created_at,  # type: ignore[attr-defined]
        content=raw.content or "",  # type: ignore[attr-defined]
        edited_at=getattr(raw, "edited_at", None),
        reply_to=reply_to,
        thread_id=thread_id,
        attachments=attachments,
        embeds=embeds,
        reactions=reactions,
    )


class DiscordClient:
    """Async context manager wrapping a discord.py Client for one-shot crawls."""

    def __init__(self, token: str) -> None:
        import discord

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        self._discord = discord
        self._client: discord.Client = discord.Client(intents=intents)
        self._token = token
        self._login_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "DiscordClient":
        self._login_task = asyncio.create_task(self._client.start(self._token))
        await self._client.wait_until_ready()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.close()
        if self._login_task is not None:
            try:
                await self._login_task
            except Exception:
                pass

    async def _get_channel(self, channel_id: str):
        ch = self._client.get_channel(int(channel_id))
        if ch is None:
            ch = await self._client.fetch_channel(int(channel_id))
        return ch

    async def fetch_channel_messages(
        self, channel_id: str, after: datetime, before: datetime
    ) -> AsyncIterator[Message]:
        ch = await self._get_channel(channel_id)
        async for raw in ch.history(
            after=after, before=before, limit=None, oldest_first=True
        ):
            try:
                yield convert_discord_message(raw)
            except Exception as e:
                # Per-message parse failure: log and skip, do not abort the channel.
                rid = getattr(raw, "id", "?")
                print(f"[crawler] WARN parse failed for msg {rid}: {e}", file=sys.stderr)

    async def fetch_active_thread_ids(self, channel_id: str) -> list[str]:
        ch = await self._get_channel(channel_id)
        threads = getattr(ch, "threads", None) or []
        return [str(t.id) for t in threads]

    async def fetch_thread_messages(
        self, thread_id: str, after: datetime, before: datetime
    ) -> AsyncIterator[Message]:
        thread = await self._get_channel(thread_id)
        async for raw in thread.history(
            after=after, before=before, limit=None, oldest_first=True
        ):
            try:
                yield convert_discord_message(raw, thread_id=thread_id)
            except Exception as e:
                rid = getattr(raw, "id", "?")
                print(f"[crawler] WARN parse failed for msg {rid}: {e}", file=sys.stderr)
```

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "from crawler.client import DiscordClient, DiscordClientProtocol, convert_discord_message; print('ok')"`
Expected: prints `ok`.

Run: `uv run pytest tests/crawler/conftest.py --collect-only`
Expected: no errors (conftest is collected without test functions).

- [ ] **Step 4: Lint + format**

Run: `uv run ruff check crawler/client.py tests/crawler/conftest.py`
Run: `uv run ruff format --check crawler/client.py tests/crawler/conftest.py`

- [ ] **Step 5: Commit**

```bash
git add crawler/client.py tests/crawler/conftest.py
git commit -m "feat(crawler): add DiscordClient adapter and FakeDiscordClient fixture"
```

---

## Task 7: Channel × week fetcher

**Files:**
- Create: `crawler/fetch.py`
- Create: `tests/crawler/test_fetch.py`

- [ ] **Step 1: Write failing tests**

Create `tests/crawler/test_fetch.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from crawler.fetch import fetch_channel_week
from crawler.models import Author, Message
from tests.crawler.conftest import FakeChannelData, FakeDiscordClient

JST = ZoneInfo("Asia/Tokyo")


def _msg(mid: str, ts: datetime, content: str = "x", thread_id: str | None = None) -> Message:
    return Message(
        id=mid,
        author=Author(id="100", username="alice", display_name="Alice"),
        timestamp=ts,
        content=content,
        thread_id=thread_id,
    )


@pytest.mark.asyncio
async def test_fetch_returns_messages_in_window() -> None:
    client = FakeDiscordClient(
        channels={
            "ch1": FakeChannelData(
                messages=[
                    _msg("a", datetime(2026, 4, 19, 23, 59, tzinfo=JST)),  # before window
                    _msg("b", datetime(2026, 4, 20, 0, 0, tzinfo=JST)),    # in (boundary)
                    _msg("c", datetime(2026, 4, 22, tzinfo=JST)),          # in
                    _msg("d", datetime(2026, 4, 27, 0, 0, tzinfo=JST)),    # exclusive end
                ]
            )
        }
    )
    start = datetime(2026, 4, 20, tzinfo=JST)
    end = datetime(2026, 4, 27, tzinfo=JST)
    msgs = await fetch_channel_week(client, channel_id="ch1", week_start=start, week_end=end)
    ids = [m.id for m in msgs]
    assert ids == ["b", "c"]


@pytest.mark.asyncio
async def test_fetch_merges_active_threads() -> None:
    client = FakeDiscordClient(
        channels={
            "ch1": FakeChannelData(
                messages=[_msg("parent", datetime(2026, 4, 22, tzinfo=JST))],
                thread_messages={
                    "th1": [
                        _msg("t1", datetime(2026, 4, 22, 1, tzinfo=JST), thread_id="th1"),
                        _msg("t2", datetime(2026, 4, 23, tzinfo=JST), thread_id="th1"),
                    ],
                    "th2": [
                        _msg("t3", datetime(2026, 4, 24, tzinfo=JST), thread_id="th2"),
                    ],
                },
            )
        }
    )
    start = datetime(2026, 4, 20, tzinfo=JST)
    end = datetime(2026, 4, 27, tzinfo=JST)
    msgs = await fetch_channel_week(client, channel_id="ch1", week_start=start, week_end=end)
    ids = sorted(m.id for m in msgs)
    assert ids == ["parent", "t1", "t2", "t3"]
    # Thread messages carry their thread_id
    by_id = {m.id: m for m in msgs}
    assert by_id["t1"].thread_id == "th1"
    assert by_id["parent"].thread_id is None


@pytest.mark.asyncio
async def test_fetch_returns_empty_for_empty_channel() -> None:
    client = FakeDiscordClient(channels={"ch1": FakeChannelData()})
    msgs = await fetch_channel_week(
        client,
        channel_id="ch1",
        week_start=datetime(2026, 4, 20, tzinfo=JST),
        week_end=datetime(2026, 4, 27, tzinfo=JST),
    )
    assert msgs == []


@pytest.mark.asyncio
async def test_fetch_sorts_results_by_timestamp() -> None:
    client = FakeDiscordClient(
        channels={
            "ch1": FakeChannelData(
                messages=[_msg("late", datetime(2026, 4, 25, tzinfo=JST))],
                thread_messages={
                    "th1": [
                        _msg("early", datetime(2026, 4, 21, tzinfo=JST), thread_id="th1"),
                    ]
                },
            )
        }
    )
    msgs = await fetch_channel_week(
        client,
        channel_id="ch1",
        week_start=datetime(2026, 4, 20, tzinfo=JST),
        week_end=datetime(2026, 4, 27, tzinfo=JST),
    )
    assert [m.id for m in msgs] == ["early", "late"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/crawler/test_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.fetch'`.

- [ ] **Step 3: Implement `crawler/fetch.py`**

Create `crawler/fetch.py`:

```python
from __future__ import annotations

from datetime import datetime

from crawler.client import DiscordClientProtocol
from crawler.models import Message


async def fetch_channel_week(
    client: DiscordClientProtocol,
    *,
    channel_id: str,
    week_start: datetime,
    week_end: datetime,
) -> list[Message]:
    """Fetch all messages in [week_start, week_end) for a channel and its
    active threads. Returned list is sorted by timestamp ascending."""
    collected: list[Message] = []

    async for msg in client.fetch_channel_messages(channel_id, week_start, week_end):
        collected.append(msg)

    thread_ids = await client.fetch_active_thread_ids(channel_id)
    for tid in thread_ids:
        async for msg in client.fetch_thread_messages(tid, week_start, week_end):
            collected.append(msg)

    collected.sort(key=lambda m: m.timestamp)
    return collected
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `uv run pytest tests/crawler/test_fetch.py -v`
Expected: 4 passed.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check crawler/fetch.py tests/crawler/test_fetch.py`
Run: `uv run ruff format --check crawler/fetch.py tests/crawler/test_fetch.py`

- [ ] **Step 6: Commit**

```bash
git add crawler/fetch.py tests/crawler/test_fetch.py
git commit -m "feat(crawler): add fetch_channel_week with thread merge and sort"
```

---

## Task 8: CLI and orchestration

**Files:**
- Create: `crawler/main.py`
- Create: `tests/crawler/test_main_cli.py`

- [ ] **Step 1: Write failing tests for argparse**

Create `tests/crawler/test_main_cli.py`:

```python
import pytest

from crawler import main as cli


def test_parse_args_defaults() -> None:
    args = cli.parse_args([])
    assert args.config is None
    assert args.week is None
    assert args.server is None
    assert args.channel is None
    assert args.force is False


def test_parse_args_force_flag() -> None:
    args = cli.parse_args(["--force"])
    assert args.force is True


def test_parse_args_week_filter() -> None:
    args = cli.parse_args(["--week", "2026-W15"])
    assert args.week == "2026-W15"


def test_parse_args_server_channel_filter() -> None:
    args = cli.parse_args(["--server", "Splatoon道場", "--channel", "戦術談義"])
    assert args.server == "Splatoon道場"
    assert args.channel == "戦術談義"


def test_parse_args_custom_config_path(tmp_path) -> None:
    args = cli.parse_args(["--config", str(tmp_path / "x.yaml")])
    assert args.config == tmp_path / "x.yaml"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/crawler/test_main_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.main'` or `AttributeError`.

- [ ] **Step 3: Implement `crawler/main.py`**

Create `crawler/main.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from crawler.client import DiscordClient, DiscordClientProtocol
from crawler.config import CrawlConfig, load_crawl_config
from crawler.fetch import fetch_channel_week
from crawler.week import iso_week_range_jst, parse_week_id
from crawler.writer import channel_week_path, write_week_file

JST = ZoneInfo("Asia/Tokyo")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="crawler", description="Discord weekly crawler for the wiki pipeline"
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to discord.yaml (default: config/discord.yaml)",
    )
    p.add_argument(
        "--week",
        default=None,
        help="ISO week like '2026-W15' (default: previous week JST)",
    )
    p.add_argument("--server", default=None, help="Filter to a single server name")
    p.add_argument("--channel", default=None, help="Filter to a single channel name")
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing week files",
    )
    return p.parse_args(argv)


def _resolve_window(week: str | None) -> tuple[str, datetime, datetime]:
    if week is not None:
        return parse_week_id(week)
    return iso_week_range_jst(datetime.now(tz=JST))


def _filter_targets(
    cfg: CrawlConfig, server: str | None, channel: str | None
) -> list[tuple[str, str, str, str]]:
    """Return [(server_id, server_name, channel_id, channel_name), ...]."""
    out: list[tuple[str, str, str, str]] = []
    for s in cfg.servers:
        if server is not None and s.name != server:
            continue
        for c in s.channels:
            if channel is not None and c.name != channel:
                continue
            out.append((s.id, s.name, c.id, c.name))
    return out


async def run_crawl(
    *,
    cfg: CrawlConfig,
    client: DiscordClientProtocol,
    week_id: str,
    week_start: datetime,
    week_end: datetime,
    targets: list[tuple[str, str, str, str]],
    force: bool,
) -> tuple[int, int, int, int]:
    """Returns (written, skipped, failed, total_messages)."""
    written = skipped = failed = total = 0
    fetched_at = datetime.now(tz=JST)

    async with client:
        for server_id, server_name, channel_id, channel_name in targets:
            path = channel_week_path(cfg.output_dir, server_name, channel_name, week_id)
            if path.exists() and not force:
                print(f"[crawler] skip (exists): {path}")
                skipped += 1
                continue
            try:
                msgs = await fetch_channel_week(
                    client,
                    channel_id=channel_id,
                    week_start=week_start,
                    week_end=week_end,
                )
            except Exception as e:
                print(f"[crawler] FAIL fetch {server_name}/{channel_name}: {e}", file=sys.stderr)
                failed += 1
                continue

            wrote = write_week_file(
                path=path,
                server_id=server_id,
                server_name=server_name,
                channel_id=channel_id,
                channel_name=channel_name,
                week_id=week_id,
                week_start=week_start,
                week_end=week_end,
                fetched_at=fetched_at,
                messages=msgs,
                force=force,
            )
            if wrote:
                print(f"[crawler] wrote {len(msgs)} msgs → {path}")
                written += 1
                total += len(msgs)
            else:
                skipped += 1
    return written, skipped, failed, total


def _make_client(token: str) -> DiscordClientProtocol:
    return DiscordClient(token)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    config_path = args.config or Path("config/discord.yaml")
    if not config_path.exists():
        print(f"[crawler] config not found: {config_path}", file=sys.stderr)
        return 2

    try:
        cfg = load_crawl_config(config_path)
    except Exception as e:
        print(f"[crawler] invalid config: {e}", file=sys.stderr)
        return 2

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("[crawler] DISCORD_BOT_TOKEN env var is required", file=sys.stderr)
        return 2

    week_id, week_start, week_end = _resolve_window(args.week)
    targets = _filter_targets(cfg, args.server, args.channel)
    if not targets:
        print("[crawler] no targets matched filters", file=sys.stderr)
        return 1

    print(f"[crawler] week={week_id} targets={len(targets)}")

    client = _make_client(token)
    written, skipped, failed, total = asyncio.run(
        run_crawl(
            cfg=cfg,
            client=client,
            week_id=week_id,
            week_start=week_start,
            week_end=week_end,
            targets=targets,
            force=args.force,
        )
    )

    print(
        f"[crawler] done: written={written} skipped={skipped} "
        f"failed={failed} messages={total}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run CLI tests and verify they pass**

Run: `uv run pytest tests/crawler/test_main_cli.py -v`
Expected: 5 passed.

- [ ] **Step 5: Verify CLI help works**

Run: `uv run python -m crawler --help`
Expected: prints argparse help with all flags (`--config`, `--week`, `--server`, `--channel`, `--force`). Exits 0.

- [ ] **Step 6: Verify config-missing error path**

Create a scratch dir and invoke the module from it:

```bash
mkdir -p /tmp/crawler-smoke && cd /tmp/crawler-smoke
uv --project "$OLDPWD" run python -m crawler; echo "exit=$?"
cd "$OLDPWD"
```

Expected: prints `[crawler] config not found: config/discord.yaml` and `exit=2`.

- [ ] **Step 7: Lint + format**

Run: `uv run ruff check crawler/main.py tests/crawler/test_main_cli.py`
Run: `uv run ruff format --check crawler/main.py tests/crawler/test_main_cli.py`

- [ ] **Step 8: Commit**

```bash
git add crawler/main.py tests/crawler/test_main_cli.py
git commit -m "feat(crawler): add CLI entrypoint with orchestration loop"
```

---

## Task 9: End-to-end test with FakeDiscordClient

**Files:**
- Create: `tests/crawler/test_e2e_fake.py`

This test exercises the full pipeline (config load → fetch → write) using `FakeDiscordClient`, no real Discord. It also confirms the orchestration loop produces the expected files on disk.

- [ ] **Step 1: Write the failing test**

Create `tests/crawler/test_e2e_fake.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from crawler import main as cli
from crawler.models import Author, Message
from tests.crawler.conftest import FakeChannelData, FakeDiscordClient

JST = ZoneInfo("Asia/Tokyo")


def _msg(mid: str, ts: datetime, content: str) -> Message:
    return Message(
        id=mid,
        author=Author(id="100", username="alice", display_name="Alice"),
        timestamp=ts,
        content=content,
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "discord.yaml").write_text(
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers:
  - id: "111"
    name: "ServerA"
    channels:
      - id: "222"
        name: "ChannelA"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-token")
    return tmp_path


def test_e2e_writes_expected_file(workspace: Path) -> None:
    client = FakeDiscordClient(
        channels={
            "222": FakeChannelData(
                messages=[
                    _msg("m1", datetime(2026, 4, 21, tzinfo=JST), "hello"),
                    _msg("m2", datetime(2026, 4, 22, tzinfo=JST), "world"),
                ]
            )
        }
    )

    with patch.object(cli, "_make_client", return_value=client):
        rc = cli.main(["--week", "2026-W17"])

    assert rc == 0
    expected = workspace / "raw_cache" / "discord" / "ServerA" / "ChannelA" / "2026-W17.md"
    assert expected.exists()
    text = expected.read_text(encoding="utf-8")
    assert "message_count: 2" in text
    assert "hello" in text
    assert "world" in text
    assert "## msg-m1" in text
    assert "## msg-m2" in text


def test_e2e_skip_existing(workspace: Path) -> None:
    target = workspace / "raw_cache" / "discord" / "ServerA" / "ChannelA" / "2026-W17.md"
    target.parent.mkdir(parents=True)
    target.write_text("already there", encoding="utf-8")

    client = FakeDiscordClient(
        channels={
            "222": FakeChannelData(
                messages=[_msg("m1", datetime(2026, 4, 21, tzinfo=JST), "x")]
            )
        }
    )
    with patch.object(cli, "_make_client", return_value=client):
        rc = cli.main(["--week", "2026-W17"])

    assert rc == 0
    assert target.read_text(encoding="utf-8") == "already there"


def test_e2e_force_overwrites(workspace: Path) -> None:
    target = workspace / "raw_cache" / "discord" / "ServerA" / "ChannelA" / "2026-W17.md"
    target.parent.mkdir(parents=True)
    target.write_text("stale", encoding="utf-8")

    client = FakeDiscordClient(
        channels={
            "222": FakeChannelData(
                messages=[_msg("m1", datetime(2026, 4, 21, tzinfo=JST), "fresh")]
            )
        }
    )
    with patch.object(cli, "_make_client", return_value=client):
        rc = cli.main(["--week", "2026-W17", "--force"])

    assert rc == 0
    text = target.read_text(encoding="utf-8")
    assert "stale" not in text
    assert "fresh" in text


def test_e2e_no_targets_returns_1(workspace: Path) -> None:
    client = FakeDiscordClient()
    with patch.object(cli, "_make_client", return_value=client):
        rc = cli.main(["--week", "2026-W17", "--server", "Nonexistent"])
    assert rc == 1


def test_e2e_missing_token_returns_2(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_BOT_TOKEN")
    rc = cli.main(["--week", "2026-W17"])
    assert rc == 2


def test_e2e_missing_config_returns_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake")
    rc = cli.main(["--week", "2026-W17"])
    assert rc == 2
```

- [ ] **Step 2: Run the e2e tests and verify they pass**

Run: `uv run pytest tests/crawler/test_e2e_fake.py -v`
Expected: 6 passed.

- [ ] **Step 3: Run the full crawler suite to confirm no regressions**

Run: `uv run pytest tests/crawler/ -v`
Expected: all crawler tests pass (cumulative across Tasks 2–9 = roughly 35+ tests).

- [ ] **Step 4: Run the full project suite (including pipeline #1 tests)**

Run: `uv run pytest -q`
Expected: 0 failures.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check tests/crawler/test_e2e_fake.py`
Run: `uv run ruff format --check tests/crawler/test_e2e_fake.py`

- [ ] **Step 6: Commit**

```bash
git add tests/crawler/test_e2e_fake.py
git commit -m "test(crawler): add end-to-end test with FakeDiscordClient"
```

---

## Task 10: Docker image and crontab example

**Files:**
- Create: `docker/crawler/Dockerfile`
- Create: `docker/crawler/crontab.example`

This task does NOT use TDD — Docker / cron files are configuration, verified by manual build + smoke test.

- [ ] **Step 1: Create the Dockerfile**

Create `docker/crawler/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv (single static binary, no deps)
RUN pip install --no-cache-dir "uv>=0.4"

# Cache dependency install layer
COPY pyproject.toml uv.lock ./
RUN uv sync --extra crawler --frozen --no-dev

# Application code
COPY crawler/ ./crawler/
COPY config/ ./config/

# Output dir is bind-mounted at runtime
VOLUME ["/app/raw_cache"]

ENTRYPOINT ["uv", "run", "python", "-m", "crawler"]
```

- [ ] **Step 2: Create the crontab example**

Create `docker/crawler/crontab.example`:

```cron
# Splatoon Discord crawler - weekly fetch of the previous ISO week (JST).
# Replace IMAGE_NAME, ENV_PATH, RAW_CACHE_PATH, LOG_PATH with your values.
#
# Install with: crontab -e
#
# Schedule: every Monday at 09:00 (host time). Adjust if host is not JST.

0 9 * * 1 docker run --rm \
  --env-file ENV_PATH \
  -v RAW_CACHE_PATH:/app/raw_cache \
  IMAGE_NAME >> LOG_PATH 2>&1
```

- [ ] **Step 3: Build the image**

Run: `docker build -t splatoon-crawler -f docker/crawler/Dockerfile .`
Expected: build succeeds, final image size roughly 200–300 MB.

- [ ] **Step 4: Smoke test the built image**

Run:
```bash
docker run --rm splatoon-crawler --help
```
Expected: prints argparse help (the same as `uv run python -m crawler --help`). Exits 0.

Run (no token, no config — confirms exit code 2):
```bash
docker run --rm splatoon-crawler 2>&1; echo "exit=$?"
```
Expected: prints `[crawler] DISCORD_BOT_TOKEN env var is required` (or `config not found` depending on which check fails first based on config baked into the image — see note below) and `exit=2`.

NOTE: If `config/discord.yaml` is committed to git (it should NOT be — only `.example`), it will be baked into the image. The expected failure mode is missing token. If you see `config not found`, it confirms `config/discord.yaml` is correctly absent from git.

- [ ] **Step 5: Commit**

```bash
git add docker/crawler/Dockerfile docker/crawler/crontab.example
git commit -m "feat(crawler): add Dockerfile and weekly crontab example"
```

---

## Completion checklist

- [ ] Tasks 1–10 committed
- [ ] `uv run pytest -q` passes (no regressions in pipeline #1 suite)
- [ ] `uv run pytest tests/crawler/ -v` passes (all crawler tests)
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run python -m crawler --help` shows all flags
- [ ] `docker build -t splatoon-crawler -f docker/crawler/Dockerfile .` succeeds
- [ ] `docker run --rm splatoon-crawler --help` works
- [ ] `config/discord.yaml.example` exists and is tracked in git
- [ ] `config/discord.yaml` (real config) is NOT tracked (it contains real server IDs and is per-deployment)
- [ ] `raw_cache/` continues to be ignored by `.gitignore`
- [ ] No real Discord API call exists in the test suite

---

## Out of scope reminders (for the executor)

If you find yourself wanting to add any of the following during implementation, STOP — they belong to later sub-projects, not this plan:

- Google Drive upload of `raw_cache/` files
- Wiring `raw_cache/` into the pipeline `Ingest` stage
- PII anonymization (it's the `Ingest` LLM's job, not the crawler's)
- A real-Discord integration test (token management is out of scope)
- A scheduler service beyond the example crontab
- Archived-thread support
- Edit-history or deletion tracking
