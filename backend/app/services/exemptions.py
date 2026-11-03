"""Calendar exemptions lookup.

docs/04_ZONES_AND_RULES.md section 5:
Exemptions for special-case calendar dates (holidays, exam days, events).
Scopes: 'all', 'camera', 'action'. Evaluated in local time.
"""

import logging
import sqlite3
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.config import config

logger = logging.getLogger(__name__)


def get_local_date_str(ts_ms: int, timezone_str: str | None = None) -> str:
    """Convert UTC epoch millisecond timestamp to local date string YYYY-MM-DD."""
    tz_name = timezone_str or config.app.get("timezone", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = UTC

    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=tz)
    return dt.strftime("%Y-%m-%d")


def is_calendar_exempt(
    camera_id: str,
    action_id: str,
    ts_ms: int,
    db_conn: sqlite3.Connection,
    timezone_str: str | None = None
) -> bool:
    """Check if the given camera, action, and timestamp fall within an active calendar exemption."""
    date_str = get_local_date_str(ts_ms, timezone_str)

    query = """
        SELECT id, label, scope FROM calendar_exemptions
        WHERE date_from <= ? AND ? <= date_to
          AND (
            scope = 'all'
            OR (scope = 'camera' AND camera_id = ?)
            OR (scope = 'action' AND action_id = ?)
          )
        LIMIT 1
    """
    row = db_conn.execute(query, (date_str, date_str, camera_id, action_id)).fetchone()
    if row:
        logger.debug(
            f"Calendar exemption '{row['label']}' (scope={row['scope']}) active for "
            f"action={action_id}, camera={camera_id} on {date_str}"
        )
        return True
    return False
