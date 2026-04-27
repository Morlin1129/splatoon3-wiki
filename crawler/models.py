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
