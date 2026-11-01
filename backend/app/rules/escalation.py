"""Pure escalation severity calculation.

docs/04 s5:
Pure function escalation.pick_severity(base, escalation, recent_event_times, now).
Evaluated over this rule's recent events; the highest matching severity wins.
"""

from app.rules.models import EscalationRow

SEVERITY_ORDER: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "critical": 3
}


def pick_severity(
    base_severity: str,
    escalation_rows: list[EscalationRow],
    recent_event_times_ms: list[int],
    now_ms: int
) -> str:
    """Determine effective severity level based on recent event count windows.
    
    Highest severity among matching escalation rows and base severity wins.
    """
    highest = base_severity
    highest_rank = SEVERITY_ORDER.get(base_severity.lower(), 1)

    for row in escalation_rows:
        cfg = row.if_count_in_window
        n = cfg.get("n", 1)
        window_min = cfg.get("window_min", 10)
        window_ms = window_min * 60 * 1000
        window_start = now_ms - window_ms

        count = sum(1 for t in recent_event_times_ms if window_start <= t <= now_ms)
        if count >= n:
            row_rank = SEVERITY_ORDER.get(row.severity.lower(), 1)
            if row_rank > highest_rank:
                highest_rank = row_rank
                highest = row.severity

    return highest
