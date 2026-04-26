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
