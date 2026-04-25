from pipeline.stages.index import _extract_summary, _extract_title


def test_extract_title_uses_first_h2() -> None:
    body = "## 海女美術 右高台\n\n本文。\n\n## セクション\n"
    assert _extract_title(body, fallback="slug") == "海女美術 右高台"


def test_extract_title_falls_back_to_h1_when_no_h2() -> None:
    body = "# Top\n\n本文。\n"
    assert _extract_title(body, fallback="slug") == "Top"


def test_extract_title_falls_back_to_slug_when_no_heading() -> None:
    body = "本文だけ。\n"
    assert _extract_title(body, fallback="my-subtopic") == "my-subtopic"


def test_extract_title_strips_trailing_whitespace() -> None:
    body = "##   海女美術  \n"
    assert _extract_title(body, fallback="x") == "海女美術"


def test_extract_summary_takes_first_sentence_after_title() -> None:
    body = "## タイトル\n\n最初の文。続きの文。\n\n## 別セクション\n"
    assert _extract_summary(body) == "最初の文。"


def test_extract_summary_handles_ascii_period() -> None:
    body = "## Title\n\nFirst sentence. Second sentence.\n"
    assert _extract_summary(body) == "First sentence."


def test_extract_summary_truncates_long_sentence() -> None:
    long_sentence = "あ" * 130 + "。"
    body = f"## タイトル\n\n{long_sentence}\n"
    result = _extract_summary(body)
    assert result.endswith("…")
    assert len(result) == 121


def test_extract_summary_returns_placeholder_when_body_empty() -> None:
    body = "## タイトル\n\n"
    assert _extract_summary(body) == "(本文なし)"


def test_extract_summary_skips_bullet_lines() -> None:
    body = "## タイトル\n\n- 箇条書きはサマリにしない\n- 二つ目\n\n通常段落。\n"
    assert _extract_summary(body) == "通常段落。"


def test_extract_summary_works_without_heading() -> None:
    body = "見出しなしの段落。続き。\n"
    assert _extract_summary(body) == "見出しなしの段落。"
