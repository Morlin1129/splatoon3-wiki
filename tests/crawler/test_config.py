from pathlib import Path

import pytest
from pydantic import ValidationError

from crawler.config import CrawlConfig, load_crawl_config


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_load_minimal_valid_config(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers:
  - id: "111"
    name: "ServerA"
    channels:
      - id: "222"
        name: "ChannelA"
""".strip(),
    )
    cfg = load_crawl_config(p)
    assert cfg.output_dir == Path("raw_cache/discord")
    assert cfg.timezone == "Asia/Tokyo"
    assert len(cfg.servers) == 1
    assert cfg.servers[0].channels[0].name == "ChannelA"


def test_load_multiple_servers_and_channels(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers:
  - id: "111"
    name: "A"
    channels:
      - id: "1"
        name: "ch1"
      - id: "2"
        name: "ch2"
  - id: "222"
    name: "B"
    channels:
      - id: "3"
        name: "ch3"
""".strip(),
    )
    cfg = load_crawl_config(p)
    assert len(cfg.servers) == 2
    assert sum(len(s.channels) for s in cfg.servers) == 3


def test_missing_servers_field_raises(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
""".strip(),
    )
    with pytest.raises(ValidationError):
        load_crawl_config(p)


def test_empty_servers_list_raises(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers: []
""".strip(),
    )
    with pytest.raises(ValidationError):
        load_crawl_config(p)


def test_numeric_id_in_yaml_raises(tmp_path: Path) -> None:
    # Snowflakes must be quoted strings; bare numbers risk precision loss
    # and are explicitly disallowed.
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
timezone: Asia/Tokyo
servers:
  - id: 123456789012345678
    name: "S"
    channels:
      - id: "1"
        name: "c"
""".strip(),
    )
    with pytest.raises(ValidationError):
        load_crawl_config(p)


def test_default_timezone_is_jst(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "discord.yaml",
        """
output_dir: raw_cache/discord
servers:
  - id: "111"
    name: "S"
    channels:
      - id: "1"
        name: "c"
""".strip(),
    )
    cfg = load_crawl_config(p)
    assert cfg.timezone == "Asia/Tokyo"


def test_crawl_config_direct_construction() -> None:
    cfg = CrawlConfig.model_validate(
        {
            "output_dir": "raw_cache/discord",
            "servers": [
                {"id": "1", "name": "S", "channels": [{"id": "2", "name": "c"}]},
            ],
        }
    )
    assert cfg.timezone == "Asia/Tokyo"
