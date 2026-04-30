from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

Provider = Literal["anthropic", "gemini", "fake"]
LevelMode = Literal["enumerated", "open"]


class LevelValue(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class FixedLevel(BaseModel):
    name: str = Field(min_length=1)
    mode: LevelMode
    values: list[LevelValue] | None = None
    values_by_parent: dict[str, list[LevelValue]] | None = None

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> "FixedLevel":
        if self.mode == "open":
            if self.values is not None or self.values_by_parent is not None:
                raise ValueError(
                    f"open mode level '{self.name}' must not have values/values_by_parent"
                )
        elif self.mode == "enumerated":
            if self.values is None and self.values_by_parent is None:
                raise ValueError(
                    f"enumerated mode level '{self.name}' must have values or values_by_parent"
                )
            if self.values is not None and self.values_by_parent is not None:
                raise ValueError(
                    f"enumerated mode level '{self.name}' cannot have both"
                    " values and values_by_parent"
                )
        return self


class Category(BaseModel):
    id: str
    label: str
    description: str
    fixed_levels: list[FixedLevel] = Field(default_factory=list)


class StageConfig(BaseModel):
    provider: Provider
    model: str
    max_tokens: int = Field(gt=0)


class PipelineConfig(BaseModel):
    stages: dict[str, StageConfig]


def _validate_values_by_parent_consistency(cats: list[Category]) -> None:
    """For each category with values_by_parent on level N, the keys must match
    the parent level's values[].id set exactly."""
    for cat in cats:
        levels = cat.fixed_levels
        for i, lvl in enumerate(levels):
            if lvl.values_by_parent is None:
                continue
            if i == 0:
                raise ValueError(
                    f"category {cat.id} level '{lvl.name}': values_by_parent"
                    " is invalid on the top level (no parent)"
                )
            parent = levels[i - 1]
            if parent.mode != "enumerated" or parent.values is None:
                raise ValueError(
                    f"category {cat.id} level '{lvl.name}': values_by_parent"
                    " requires parent level to be enumerated with flat values"
                )
            parent_ids = {v.id for v in parent.values}
            child_keys = set(lvl.values_by_parent.keys())
            if parent_ids != child_keys:
                missing = parent_ids - child_keys
                extra = child_keys - parent_ids
                raise ValueError(
                    f"category {cat.id} level '{lvl.name}': values_by_parent"
                    f" keys must match parent ids exactly. missing={sorted(missing)}"
                    f" extra={sorted(extra)}"
                )


def load_categories(path: Path) -> list[Category]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cats = [Category.model_validate(item) for item in data["categories"]]
    _validate_values_by_parent_consistency(cats)
    return cats


def load_pipeline(path: Path) -> PipelineConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PipelineConfig.model_validate(data)


def build_system_prompt(root: Path, stage_name: str) -> str:
    """Compose system prompt: shared domain + stage domain + pipeline rules."""
    parts: list[str] = []
    for candidate in (
        root / "config" / "domain.md",
        root / "config" / "domain" / f"{stage_name}.md",
    ):
        if candidate.exists():
            parts.append(candidate.read_text(encoding="utf-8").strip())
    rules = root / "pipeline" / "prompts" / f"{stage_name}.md"
    parts.append(rules.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts) + "\n"
