from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Provider = Literal["anthropic", "gemini", "fake"]


class Category(BaseModel):
    id: str
    label: str
    description: str


class StageConfig(BaseModel):
    provider: Provider
    model: str
    max_tokens: int = Field(gt=0)


class PipelineConfig(BaseModel):
    stages: dict[str, StageConfig]


def load_categories(path: Path) -> list[Category]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Category.model_validate(item) for item in data["categories"]]


def load_pipeline(path: Path) -> PipelineConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PipelineConfig.model_validate(data)
