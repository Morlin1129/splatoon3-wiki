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
    assert 'server_id: "111"' in text
    assert 'channel_id: "222"' in text
    assert "week: 2026-W17" in text or 'week: "2026-W17"' in text
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
            "222": FakeChannelData(messages=[_msg("m1", datetime(2026, 4, 21, tzinfo=JST), "x")])
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


@pytest.fixture
def workspace_two_channels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
      - id: "333"
        name: "ChannelB"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-token")
    return tmp_path


def test_e2e_fetch_failure_returns_1_and_continues(workspace_two_channels: Path) -> None:
    """If fetch fails for one channel, the loop continues to the next and the
    overall exit code is 1 (partial failure)."""

    class FlakyClient(FakeDiscordClient):
        async def fetch_channel_messages(self, channel_id, after, before):
            if channel_id == "222":
                raise RuntimeError("simulated fetch failure")
            async for m in super().fetch_channel_messages(channel_id, after, before):
                yield m

    client = FlakyClient(
        channels={
            "333": FakeChannelData(messages=[_msg("ok1", datetime(2026, 4, 22, tzinfo=JST), "ok")])
        }
    )
    with patch.object(cli, "_make_client", return_value=client):
        rc = cli.main(["--week", "2026-W17"])

    assert rc == 1  # partial failure
    # ChannelA file NOT written (fetch failed)
    cha = workspace_two_channels / "raw_cache" / "discord" / "ServerA" / "ChannelA" / "2026-W17.md"
    assert not cha.exists()
    # ChannelB file IS written (fetch succeeded after the loop continued)
    chb = workspace_two_channels / "raw_cache" / "discord" / "ServerA" / "ChannelB" / "2026-W17.md"
    assert chb.exists()
    text = chb.read_text(encoding="utf-8")
    assert "## msg-ok1" in text
