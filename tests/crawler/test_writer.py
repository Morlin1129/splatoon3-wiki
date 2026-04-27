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
    assert "channel_name: C" in text or 'channel_name: "C"' in text
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


def test_write_week_file_preserves_horizontal_rule_in_body(tmp_path: Path) -> None:
    """A user posting `---` in a message body must not break the message
    structure: only the two frontmatter delimiters should appear as
    unindented `---` lines in the file."""
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
        messages=[
            _msg(id="1", content="before\n---\nafter"),
            _msg(id="2", content="another"),
        ],
    )
    text = path.read_text(encoding="utf-8")
    # Frontmatter delimiters: opening `---\n` at start, closing `---` line.
    # The body's internal `---` is allowed; what's NOT allowed is having
    # MORE than 2 frontmatter-style fences (i.e., extra unindented `---`
    # lines that a line splitter could mistake for frontmatter).
    fence_lines = [line for line in text.splitlines() if line == "---"]
    assert len(fence_lines) == 3  # opening fence, closing fence, body's `---`
    # Ensure both messages survived as distinct blocks.
    assert "## msg-1" in text
    assert "## msg-2" in text
    assert "before" in text
    assert "after" in text
    assert "another" in text
