from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import yaml

from crawler.models import Message


class _DoubleQuoteDumper(yaml.SafeDumper):
    """SafeDumper that uses double quotes when a string scalar needs quoting."""


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    # Decide whether the bare scalar would be ambiguous (resolves to non-str
    # tag like int/float/bool/null). If so, force double-quoted style; otherwise
    # leave it as a plain scalar.
    resolved = dumper.resolve(yaml.nodes.ScalarNode, data, (True, False))
    style = '"' if resolved != "tag:yaml.org,2002:str" else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_DoubleQuoteDumper.add_representer(str, _str_representer)

_PATH_UNSAFE = ("/", "\\")


def _slugify(name: str) -> str:
    out = name
    for ch in _PATH_UNSAFE:
        out = out.replace(ch, "_")
    return out


def channel_week_path(out_dir: Path, server_name: str, channel_name: str, week_id: str) -> Path:
    return out_dir / _slugify(server_name) / _slugify(channel_name) / f"{week_id}.md"


def format_message_block(msg: Message) -> str:
    lines: list[str] = [f"## msg-{msg.id}", ""]
    lines.append(f'- author_id: "{msg.author.id}"')
    lines.append(f'- author_username: "{msg.author.username}"')
    lines.append(f'- author_display_name: "{msg.author.display_name}"')
    lines.append(f'- timestamp: "{msg.timestamp.isoformat()}"')
    if msg.edited_at is not None:
        lines.append(f'- edited_at: "{msg.edited_at.isoformat()}"')
    if msg.reply_to is not None:
        lines.append(f'- reply_to: "{msg.reply_to}"')
    if msg.thread_id is not None:
        lines.append(f'- thread_id: "{msg.thread_id}"')
    if msg.attachments:
        lines.append("- attachments:")
        for a in msg.attachments:
            lines.append(f'  - "{a.url}"')
    if msg.embeds:
        lines.append("- embeds:")
        for u in msg.embeds:
            lines.append(f'  - "{u}"')
    if msg.reactions:
        lines.append("- reactions:")
        for r in msg.reactions:
            lines.append(f'  - "{r.emoji}": {r.count}')
    lines.append("")
    lines.append(msg.content)
    return "\n".join(lines)


def write_week_file(
    *,
    path: Path,
    server_id: str,
    server_name: str,
    channel_id: str,
    channel_name: str,
    week_id: str,
    week_start: datetime,
    week_end: datetime,
    fetched_at: datetime,
    messages: list[Message],
    force: bool = False,
) -> bool:
    """Write a week file. Returns True if written, False if skipped."""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "server_id": server_id,
        "server_name": server_name,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "week": week_id,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "fetched_at": fetched_at.isoformat(),
        "message_count": len(messages),
    }
    fm_yaml = yaml.dump(
        frontmatter,
        Dumper=_DoubleQuoteDumper,
        allow_unicode=True,
        sort_keys=False,
    )
    blocks = [format_message_block(m) for m in messages]
    body = "\n\n".join(blocks)
    content = f"---\n{fm_yaml}---\n\n{body}\n" if blocks else f"---\n{fm_yaml}---\n"

    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(content, encoding="utf-8")
    os.replace(partial, path)
    return True
