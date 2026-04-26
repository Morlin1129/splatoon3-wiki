from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from crawler.week import iso_week_range_jst, parse_week_id

JST = ZoneInfo("Asia/Tokyo")


def test_returns_previous_iso_week_for_midweek_jst() -> None:
    # 2026-04-26 is a Sunday in JST and falls in 2026-W17 (Mon 4/20 ~ Sun 4/26).
    # The function returns the ISO week strictly preceding `now`, so 2026-W16.
    now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=JST)
    week_id, start, end = iso_week_range_jst(now)
    assert week_id == "2026-W16"
    assert start == datetime(2026, 4, 13, 0, 0, 0, tzinfo=JST)
    assert end == datetime(2026, 4, 20, 0, 0, 0, tzinfo=JST)


def test_handles_monday_start_of_week() -> None:
    # Monday 2026-04-27 00:30 JST: previous week = W17 (4/20 ~ 4/26).
    now = datetime(2026, 4, 27, 0, 30, 0, tzinfo=JST)
    week_id, start, end = iso_week_range_jst(now)
    assert week_id == "2026-W17"
    assert start == datetime(2026, 4, 20, 0, 0, 0, tzinfo=JST)
    assert end == datetime(2026, 4, 27, 0, 0, 0, tzinfo=JST)


def test_handles_year_boundary() -> None:
    # Mon 2026-01-05 09:00 JST → previous week = 2025-W53 (since 2025 has 53 ISO weeks)
    now = datetime(2026, 1, 5, 9, 0, 0, tzinfo=JST)
    week_id, start, end = iso_week_range_jst(now)
    # Verify week_id format and that start/end are 7 days apart and Mondays.
    assert "-W" in week_id
    assert (end - start).days == 7
    assert start.weekday() == 0  # Monday
    assert end.weekday() == 0


def test_converts_utc_now_to_jst_before_computing() -> None:
    # 2026-04-27 00:00 UTC = 2026-04-27 09:00 JST (Monday morning).
    # Previous week = W17.
    now_utc = datetime(2026, 4, 27, 0, 0, 0, tzinfo=UTC)
    week_id, _, _ = iso_week_range_jst(now_utc)
    assert week_id == "2026-W17"


def test_naive_datetime_raises() -> None:
    with pytest.raises(ValueError):
        iso_week_range_jst(datetime(2026, 4, 26, 12, 0, 0))


def test_parse_week_id_roundtrip() -> None:
    week_id, start, end = parse_week_id("2026-W17")
    assert week_id == "2026-W17"
    assert start == datetime(2026, 4, 20, 0, 0, 0, tzinfo=JST)
    assert end == datetime(2026, 4, 27, 0, 0, 0, tzinfo=JST)


def test_parse_week_id_invalid_format() -> None:
    with pytest.raises(ValueError):
        parse_week_id("2026-17")
    with pytest.raises(ValueError):
        parse_week_id("not-a-week")
