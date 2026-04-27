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

    async def __aenter__(self) -> FakeDiscordClient:
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
