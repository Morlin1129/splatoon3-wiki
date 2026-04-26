from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def iso_week_range_jst(now: datetime) -> tuple[str, datetime, datetime]:
    """Return (week_id, start, end) for the ISO week strictly preceding `now`.

    All datetimes are JST-aware. `start` is Monday 00:00, `end` is the next
    Monday 00:00 (exclusive). `week_id` is "YYYY-Www" using ISO 8601 numbering.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now_jst = now.astimezone(JST)
    days_since_monday = now_jst.weekday()  # Monday = 0
    this_monday = (now_jst - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    prev_monday = this_monday - timedelta(days=7)
    iso_year, iso_week, _ = prev_monday.isocalendar()
    week_id = f"{iso_year}-W{iso_week:02d}"
    return week_id, prev_monday, this_monday


def parse_week_id(week_id: str) -> tuple[str, datetime, datetime]:
    """Parse 'YYYY-Wnn' into (week_id, start, end) JST-aware.

    `start` is Monday 00:00 JST of that ISO week; `end` is the next Monday.
    """
    parts = week_id.split("-W")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"invalid week_id: {week_id!r}")
    year, week = int(parts[0]), int(parts[1])
    start_naive = datetime.fromisocalendar(year, week, 1)  # Monday
    start = start_naive.replace(tzinfo=JST)
    end = start + timedelta(days=7)
    return week_id, start, end
