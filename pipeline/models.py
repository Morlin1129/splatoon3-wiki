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
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subtopic: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    updated_at: datetime
    tombstone: bool = False
    merged_into: str | None = None
    merged_at: datetime | None = None
