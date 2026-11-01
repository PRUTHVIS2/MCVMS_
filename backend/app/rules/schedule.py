"""Pure schedule, validity, and exemption evaluation.

No clocks used. All timestamps passed explicitly as integer epoch milliseconds.
Evaluates local times in the specified timezone (default: Asia/Kolkata).
"""

import zoneinfo
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta, timezone

from app.rules.models import RegisteredActionSpec, ScheduleSpec, ValidSpec

DAY_MAP = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def resolve_timezone(tz_name: str = "Asia/Kolkata"):
    """Resolve timezone with safe fallback for systems without tzdata."""
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        if tz_name in ("Asia/Kolkata", "Asia/Calcutta", "IST"):
            return timezone(timedelta(hours=5, minutes=30), name="IST")
        return UTC


def parse_time_str(t_str: str) -> time:
    """Parse HH:MM string to datetime.time."""
    parts = t_str.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def is_in_schedule(spec: ScheduleSpec | None, ts_ms: int) -> bool:
    """Check if timestamp falls within the schedule window.
    
    If spec is None, the rule is always armed.
    """
    if spec is None:
        return True

    tz = resolve_timezone(spec.timezone)
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=tz)

    # 1. Day of week check
    weekday_str = DAY_MAP[dt.weekday()]
    allowed_days = [d.strip().lower() for d in spec.days]
    if weekday_str not in allowed_days:
        return False

    # 2. Time of day check
    if spec.from_time and spec.to_time:
        from_t = parse_time_str(spec.from_time)
        to_t = parse_time_str(spec.to_time)
        curr_t = dt.time()

        if from_t <= to_t:
            # Normal range during the same day (e.g. 09:00 to 17:00)
            if not (from_t <= curr_t <= to_t):
                return False
        else:
            # Wraps around midnight (e.g. 22:00 to 04:00)
            if not (curr_t >= from_t or curr_t <= to_t):
                return False

    return True


def is_in_valid_dates(spec: ValidSpec | None, ts_ms: int, timezone_name: str = "Asia/Kolkata") -> bool:
    """Check if timestamp falls within calendar validity dates (from_date..until_date inclusive)."""
    if spec is None:
        return True

    tz = resolve_timezone(timezone_name)
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=tz)
    date_str = dt.strftime("%Y-%m-%d")

    if spec.from_date and date_str < spec.from_date:
        return False
    if spec.until_date and date_str > spec.until_date:
        return False

    return True


def is_rule_armed(
    spec: RegisteredActionSpec,
    ts_ms: int,
    exempt: Callable[[str, int], bool] | None = None
) -> bool:
    """Full check whether a rule is armed and active at ts_ms."""
    tz = spec.schedule.timezone if spec.schedule else "Asia/Kolkata"

    # Calendar dates
    if not is_in_valid_dates(spec.valid, ts_ms, timezone_name=tz):
        return False

    # Armed schedule (days & hours)
    if not is_in_schedule(spec.schedule, ts_ms):
        return False

    # Calendar exemptions (holidays, exams, special events)
    if exempt is not None and spec.exemptions and spec.exemptions.calendar_ids:
        for cal_id in spec.exemptions.calendar_ids:
            if exempt(cal_id, ts_ms):
                return False  # Suppressed by exemption

    return True
