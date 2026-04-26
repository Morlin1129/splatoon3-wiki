from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from crawler.models import Attachment, Author, Message, Reaction


def test_message_minimal_fields() -> None:
    msg = Message(
        id="1234",
        author=Author(id="111", username="alice", display_name="Alice"),
        timestamp=datetime(2026, 4, 22, 14, 32, 11, tzinfo=UTC),
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
        timestamp=datetime(2026, 4, 22, tzinfo=UTC),
        content="body",
        edited_at=datetime(2026, 4, 22, 1, tzinfo=UTC),
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
            timestamp=datetime(2026, 4, 22, tzinfo=UTC),
            content="body",
        )
