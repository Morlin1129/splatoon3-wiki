from __future__ import annotations


def _extract_title(body: str, *, fallback: str) -> str:
    """Return the first `## ` heading text, else first `# `, else fallback."""
    for prefix in ("## ", "# "):
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(prefix):
                return stripped[len(prefix) :].strip()
    return fallback


_NO_BODY = "(本文なし)"
_PARAGRAPH_BREAK_PREFIXES = ("#", "-", "*", ">", "|", "```")
_SUMMARY_MAX_CHARS = 120


def _extract_summary(body: str) -> str:
    """Return the first sentence of the first non-heading paragraph.

    Falls back to "(本文なし)" if no eligible paragraph is found.
    Sentences end on a Japanese full stop `。` or an ASCII `.` followed by
    whitespace or end-of-string. The result is truncated to 120 Unicode
    code points with "…" appended when the source sentence is longer.
    """
    lines = body.splitlines()
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("## ", "# ")):
            start = i + 1
            break

    paragraph_lines: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(_PARAGRAPH_BREAK_PREFIXES):
            if paragraph_lines:
                break
            continue
        paragraph_lines.append(stripped)

    if not paragraph_lines:
        return _NO_BODY

    paragraph = " ".join(paragraph_lines)
    sentence = paragraph
    for idx, ch in enumerate(paragraph):
        if ch == "。":
            sentence = paragraph[: idx + 1]
            break
        if ch == "." and (idx + 1 >= len(paragraph) or paragraph[idx + 1].isspace()):
            sentence = paragraph[: idx + 1]
            break

    if len(sentence) > _SUMMARY_MAX_CHARS:
        sentence = sentence[:_SUMMARY_MAX_CHARS] + "…"
    return sentence
