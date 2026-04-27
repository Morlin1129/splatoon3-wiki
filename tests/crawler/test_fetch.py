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
                    _msg("b", datetime(2026, 4, 20, 0, 0, tzinfo=JST)),  # in (boundary)
                    _msg("c", datetime(2026, 4, 22, tzinfo=JST)),  # in
                    _msg("d", datetime(2026, 4, 27, 0, 0, tzinfo=JST)),  # exclusive end
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
