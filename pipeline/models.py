from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SnippetFrontmatter(BaseModel):
    source_file: str = Field(min_length=1)
    source_date: str = Field(min_length=1)
    extracted_at: datetime
    content_hash: str = Field(min_length=1)


class ClassifiedFrontmatter(SnippetFrontmatter):
    category: str = Field(min_length=1)
    path: list[str] = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def _no_empty_components(cls, v: list[str]) -> list[str]:
        for component in v:
            if not component:
                raise ValueError("path component must be non-empty")
            if "/" in component:
                raise ValueError(f"path component must not contain '/': {component!r}")
        return v


class WikiFrontmatter(BaseModel):
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    path: list[str] = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    updated_at: datetime
    tombstone: bool = False
    merged_into_path: list[str] | None = None
    merged_at: datetime | None = None

    @field_validator("path")
    @classmethod
    def _no_empty_components(cls, v: list[str]) -> list[str]:
        for component in v:
            if not component:
                raise ValueError("path component must be non-empty")
            if "/" in component:
                raise ValueError(f"path component must not contain '/': {component!r}")
        return v
