from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol

from crawler.models import Attachment, Author, Message, Reaction


class DiscordClientProtocol(Protocol):
    async def __aenter__(self) -> DiscordClientProtocol: ...
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

    async def __aenter__(self) -> DiscordClient:
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
        async for raw in ch.history(after=after, before=before, limit=None, oldest_first=True):
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
        async for raw in thread.history(after=after, before=before, limit=None, oldest_first=True):
            try:
                yield convert_discord_message(raw, thread_id=thread_id)
            except Exception as e:
                rid = getattr(raw, "id", "?")
                print(f"[crawler] WARN parse failed for msg {rid}: {e}", file=sys.stderr)
