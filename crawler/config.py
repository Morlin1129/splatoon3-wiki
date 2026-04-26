from pathlib import Path

import yaml
from pydantic import BaseModel, Field, StrictStr


class ChannelConfig(BaseModel):
    id: StrictStr = Field(min_length=1)
    name: StrictStr = Field(min_length=1)


class ServerConfig(BaseModel):
    id: StrictStr = Field(min_length=1)
    name: StrictStr = Field(min_length=1)
    channels: list[ChannelConfig] = Field(min_length=1)


class CrawlConfig(BaseModel):
    output_dir: Path
    timezone: StrictStr = "Asia/Tokyo"
    servers: list[ServerConfig] = Field(min_length=1)


def load_crawl_config(path: Path) -> CrawlConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CrawlConfig.model_validate(data)
