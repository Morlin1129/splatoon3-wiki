from pathlib import Path
from typing import TypeVar

import frontmatter
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def write_frontmatter(path: Path, fm: BaseModel, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body, **fm.model_dump(mode="json"))
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def read_frontmatter(path: Path, model: type[T], *, require: bool = True) -> tuple[T | None, str]:
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    body = post.content
    if not post.metadata:
        if require:
            raise ValueError(f"{path} has no frontmatter")
        return None, body
    return model.model_validate(post.metadata), body
