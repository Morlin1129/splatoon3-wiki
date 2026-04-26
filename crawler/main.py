from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from crawler.client import DiscordClient, DiscordClientProtocol
from crawler.config import CrawlConfig, load_crawl_config
from crawler.fetch import fetch_channel_week
from crawler.week import iso_week_range_jst, parse_week_id
from crawler.writer import channel_week_path, write_week_file

JST = ZoneInfo("Asia/Tokyo")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="crawler", description="Discord weekly crawler for the wiki pipeline"
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to discord.yaml (default: config/discord.yaml)",
    )
    p.add_argument(
        "--week",
        default=None,
        help="ISO week like '2026-W15' (default: previous week JST)",
    )
    p.add_argument("--server", default=None, help="Filter to a single server name")
    p.add_argument("--channel", default=None, help="Filter to a single channel name")
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing week files",
    )
    return p.parse_args(argv)


def _resolve_window(week: str | None) -> tuple[str, datetime, datetime]:
    if week is not None:
        return parse_week_id(week)
    return iso_week_range_jst(datetime.now(tz=JST))


def _filter_targets(
    cfg: CrawlConfig, server: str | None, channel: str | None
) -> list[tuple[str, str, str, str]]:
    """Return [(server_id, server_name, channel_id, channel_name), ...]."""
    out: list[tuple[str, str, str, str]] = []
    for s in cfg.servers:
        if server is not None and s.name != server:
            continue
        for c in s.channels:
            if channel is not None and c.name != channel:
                continue
            out.append((s.id, s.name, c.id, c.name))
    return out


async def run_crawl(
    *,
    cfg: CrawlConfig,
    client: DiscordClientProtocol,
    week_id: str,
    week_start: datetime,
    week_end: datetime,
    targets: list[tuple[str, str, str, str]],
    force: bool,
) -> tuple[int, int, int, int]:
    """Returns (written, skipped, failed, total_messages)."""
    written = skipped = failed = total = 0
    fetched_at = datetime.now(tz=JST)

    async with client:
        for server_id, server_name, channel_id, channel_name in targets:
            path = channel_week_path(cfg.output_dir, server_name, channel_name, week_id)
            if path.exists() and not force:
                print(f"[crawler] skip (exists): {path}")
                skipped += 1
                continue
            try:
                msgs = await fetch_channel_week(
                    client,
                    channel_id=channel_id,
                    week_start=week_start,
                    week_end=week_end,
                )
            except Exception as e:
                print(f"[crawler] FAIL fetch {server_name}/{channel_name}: {e}", file=sys.stderr)
                failed += 1
                continue

            wrote = write_week_file(
                path=path,
                server_id=server_id,
                server_name=server_name,
                channel_id=channel_id,
                channel_name=channel_name,
                week_id=week_id,
                week_start=week_start,
                week_end=week_end,
                fetched_at=fetched_at,
                messages=msgs,
                force=force,
            )
            if wrote:
                print(f"[crawler] wrote {len(msgs)} msgs → {path}")
                written += 1
                total += len(msgs)
            else:
                skipped += 1
    return written, skipped, failed, total


def _make_client(token: str) -> DiscordClientProtocol:
    return DiscordClient(token)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    config_path = args.config or Path("config/discord.yaml")
    if not config_path.exists():
        print(f"[crawler] config not found: {config_path}", file=sys.stderr)
        return 2

    try:
        cfg = load_crawl_config(config_path)
    except Exception as e:
        print(f"[crawler] invalid config: {e}", file=sys.stderr)
        return 2

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("[crawler] DISCORD_BOT_TOKEN env var is required", file=sys.stderr)
        return 2

    week_id, week_start, week_end = _resolve_window(args.week)
    targets = _filter_targets(cfg, args.server, args.channel)
    if not targets:
        print("[crawler] no targets matched filters", file=sys.stderr)
        return 1

    print(f"[crawler] week={week_id} targets={len(targets)}")

    client = _make_client(token)
    written, skipped, failed, total = asyncio.run(
        run_crawl(
            cfg=cfg,
            client=client,
            week_id=week_id,
            week_start=week_start,
            week_end=week_end,
            targets=targets,
            force=args.force,
        )
    )

    print(f"[crawler] done: written={written} skipped={skipped} failed={failed} messages={total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
