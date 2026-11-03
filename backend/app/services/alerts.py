"""Alerts service for real-time alerting, anti-flooding, escalation, and lifecycle.

docs/04_ZONES_AND_RULES.md section 5, docs/05_VEHICLES.md section 8, docs/08_API_AND_UI.md section 5:
- One-line human-readable messages without jargon.
- Anti-flooding: at most one open alert per (kind, target).
- Severity: low, medium, critical.
- Escalation via escalation.pick_severity.
- TTL auto-expiry and cooldown.
- Acknowledge and dismiss (role and reason required).
"""

import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import ulid

from app.api.ws import manager as ws_manager
from app.config import config
from app.services.notifier import EmailNotifier, MultiNotifier, Notifier, TelegramNotifier

logger = logging.getLogger(__name__)


def format_local_time(ts_ms: int, timezone_str: str | None = None) -> str:
    """Format UTC epoch ms as local HH:MM."""
    tz_name = timezone_str or config.app.get("timezone", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = UTC
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=tz)
    return dt.strftime("%H:%M")


def format_rule_alert_message(
    rule_name: str,
    camera_name: str,
    zone_name: str,
    ts_ms: int,
    severity: str,
    escalated: bool = False,
    subject_info: dict[str, Any] | None = None,
    is_id_rule: bool = False,
    timezone_str: str | None = None
) -> str:
    """Generate concise one-line alert message per docs/08 section 5."""
    time_str = format_local_time(ts_ms, timezone_str)

    if is_id_rule:
        msg = f"Person without visible ID · {camera_name} · {zone_name} · {time_str}"
        return f"{msg} (escalated)" if escalated else msg

    # Check vehicle attributes if present
    vehicle_details = []
    if subject_info:
        attrs = subject_info.get("attributes", {})
        cat = attrs.get("category", {}).get("value") or subject_info.get("cls")
        if cat:
            vehicle_details.append(str(cat))
        col = attrs.get("colour", {}).get("value") or subject_info.get("colour")
        if col:
            vehicle_details.append(str(col))
        plt = attrs.get("plate", {}).get("value") or subject_info.get("plate")
        if plt:
            vehicle_details.append(str(plt))
        elif subject_info.get("kind") == "vehicle" or subject_info.get("cls") in ("car", "truck", "bus", "two_wheeler", "auto_rickshaw"):
            vehicle_details.append("plate unknown")

    prefix = f"{' '.join(vehicle_details)} · " if vehicle_details else ""
    sev_upper = severity.upper()
    base = f"{prefix}{rule_name} · {camera_name} · {zone_name} · {time_str}"
    if escalated:
        base = f"{base} (escalated)"
    return f"[{sev_upper}] {base}"


class AlertService:
    """Service managing alert persistence, deduplication, and notification dispatch."""

    def __init__(self, notifier: Notifier | None = None):
        self.notifier = notifier or MultiNotifier([
            EmailNotifier(enabled=False),
            TelegramNotifier(enabled=False)
        ])

    def create_alert(
        self,
        db_conn: sqlite3.Connection,
        level: str,
        kind: str,
        message: str,
        target_type: str,
        target_id: str,
        event_id: str | None = None,
        now_ms: int | None = None,
        alert_ttl_min: int | None = None
    ) -> dict[str, Any]:
        """Create or update an alert with anti-flooding enforcement."""
        if level not in ("low", "medium", "critical"):
            level = "medium"

        now = now_ms if now_ms is not None else int(datetime.now(UTC).timestamp() * 1000)

        # 1. Anti-flooding check: one open alert per (kind, target_type, target_id)
        existing = db_conn.execute(
            """
            SELECT id, count, expires_at, event_id FROM alerts
            WHERE kind = ? AND target_type = ? AND target_id = ? AND status = 'open'
            LIMIT 1
            """,
            (kind, target_type, target_id)
        ).fetchone()

        if existing:
            # Update existing alert
            alert_id = existing["id"]
            new_count = existing["count"] + 1

            new_expires = None
            if alert_ttl_min and alert_ttl_min > 0:
                new_expires = now + int(alert_ttl_min * 60 * 1000)
            elif existing["expires_at"]:
                new_expires = existing["expires_at"]

            target_event_id = event_id if event_id is not None else existing["event_id"]
            db_conn.execute(
                """
                UPDATE alerts
                SET count = ?, message = ?, created_at = ?, expires_at = ?, level = ?, event_id = ?
                WHERE id = ?
                """,
                (new_count, message, now, new_expires, level, target_event_id, alert_id)
            )
            db_conn.commit()

            updated = self.get_alert_by_id(db_conn, alert_id)
            if updated:
                ws_manager.broadcast_alert("alert.updated", updated)
            return updated or {}

        # 2. Fresh alert
        alert_id = str(ulid.ULID())
        expires_at = (now + int(alert_ttl_min * 60 * 1000)) if (alert_ttl_min and alert_ttl_min > 0) else None

        db_conn.execute(
            """
            INSERT INTO alerts (
                id, level, kind, message, target_type, target_id, event_id,
                status, created_at, expires_at, count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, 1)
            """,
            (alert_id, level, kind, message, target_type, target_id, event_id, now, expires_at)
        )
        db_conn.commit()

        alert_data = {
            "id": alert_id,
            "level": level,
            "kind": kind,
            "message": message,
            "target_type": target_type,
            "target_id": target_id,
            "event_id": event_id,
            "status": "open",
            "created_at": now,
            "expires_at": expires_at,
            "ack_by": None,
            "ack_at": None,
            "dismiss_reason": None,
            "count": 1
        }

        # WebSocket broadcast
        ws_manager.broadcast_alert("alert.created", alert_data)

        # Dispatch external notifiers
        try:
            self.notifier.send_alert(alert_data)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to dispatch alert notification: {e}")

        return alert_data

    def get_alert_by_id(self, db_conn: sqlite3.Connection, alert_id: str) -> dict[str, Any] | None:
        """Fetch alert row by id."""
        row = db_conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return dict(row) if row else None

    def get_alerts(
        self,
        db_conn: sqlite3.Connection,
        status: str | None = None,
        level: str | None = None,
        kind: str | None = None,
        camera_id: str | None = None,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """Query alerts with filtering."""
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if level:
            clauses.append("level = ?")
            params.append(level)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if camera_id:
            clauses.append(
                "((target_type = 'camera' AND target_id = ?) OR event_id IN (SELECT id FROM events WHERE camera_id = ?))"
            )
            params.extend([camera_id, camera_id])

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM alerts {where_clause} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = db_conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def expire_alerts(self, now_ms: int, db_conn: sqlite3.Connection) -> list[str]:
        """Find and expire alerts past their TTL."""
        expired_rows = db_conn.execute(
            "SELECT id FROM alerts WHERE status = 'open' AND expires_at IS NOT NULL AND expires_at <= ?",
            (now_ms,)
        ).fetchall()

        expired_ids = [r["id"] for r in expired_rows]
        if not expired_ids:
            return []

        for aid in expired_ids:
            db_conn.execute("UPDATE alerts SET status = 'expired' WHERE id = ?", (aid,))
            updated = self.get_alert_by_id(db_conn, aid)
            if updated:
                ws_manager.broadcast_alert("alert.updated", updated)

        db_conn.commit()
        logger.info(f"Expired {len(expired_ids)} alerts past TTL at {now_ms}")
        return expired_ids

    def acknowledge_alert(
        self,
        alert_id: str,
        user_id: str,
        now_ms: int,
        db_conn: sqlite3.Connection
    ) -> dict[str, Any]:
        """Acknowledge an open alert (allowed for incharge, admin, owner)."""
        row = self.get_alert_by_id(db_conn, alert_id)
        if not row:
            raise KeyError(f"Alert {alert_id} not found")

        db_conn.execute(
            "UPDATE alerts SET status = 'acknowledged', ack_by = ?, ack_at = ? WHERE id = ?",
            (user_id, now_ms, alert_id)
        )
        db_conn.commit()

        updated = self.get_alert_by_id(db_conn, alert_id) or {}
        ws_manager.broadcast_alert("alert.updated", updated)
        return updated

    def dismiss_alert(
        self,
        alert_id: str,
        user_id: str,
        reason: str,
        now_ms: int,
        role: str,
        db_conn: sqlite3.Connection
    ) -> dict[str, Any]:
        """Dismiss an alert. Requires role in ('owner', 'admin') and a non-empty reason."""
        if role not in ("owner", "admin"):
            raise PermissionError("Only owner or admin can dismiss alerts")

        if not reason or not reason.strip():
            raise ValueError("Dismiss reason is required")

        row = self.get_alert_by_id(db_conn, alert_id)
        if not row:
            raise KeyError(f"Alert {alert_id} not found")

        db_conn.execute(
            "UPDATE alerts SET status = 'dismissed', dismiss_reason = ?, ack_by = ?, ack_at = ? WHERE id = ?",
            (reason.strip(), user_id, now_ms, alert_id)
        )
        db_conn.commit()

        updated = self.get_alert_by_id(db_conn, alert_id) or {}
        ws_manager.broadcast_alert("alert.updated", updated)
        return updated

    # --- System alert helpers ---

    def raise_camera_offline(
        self,
        camera_id: str,
        camera_name: str,
        now_ms: int,
        db_conn: sqlite3.Connection
    ) -> dict[str, Any]:
        """Raise medium camera_offline alert."""
        time_str = format_local_time(now_ms)
        message = f"{camera_name} offline since {time_str}"
        return self.create_alert(
            db_conn=db_conn,
            level="medium",
            kind="camera_offline",
            message=message,
            target_type="camera",
            target_id=camera_id,
            now_ms=now_ms
        )

    def clear_camera_offline(
        self,
        camera_id: str,
        db_conn: sqlite3.Connection
    ) -> None:
        """Dismiss active camera_offline alert when camera comes back online."""
        row = db_conn.execute(
            "SELECT id FROM alerts WHERE kind = 'camera_offline' AND target_id = ? AND status = 'open'",
            (camera_id,)
        ).fetchone()
        if row:
            db_conn.execute(
                "UPDATE alerts SET status = 'dismissed', dismiss_reason = 'Camera back online' WHERE id = ?",
                (row["id"],)
            )
            db_conn.commit()
            updated = self.get_alert_by_id(db_conn, row["id"])
            if updated:
                ws_manager.broadcast_alert("alert.updated", updated)

    def raise_disk_low(
        self,
        free_gb: float,
        now_ms: int,
        db_conn: sqlite3.Connection
    ) -> dict[str, Any]:
        """Raise critical disk_low alert."""
        message = f"Disk low: {free_gb:.1f} GB remaining"
        return self.create_alert(
            db_conn=db_conn,
            level="critical",
            kind="disk_low",
            message=message,
            target_type="system",
            target_id="disk",
            now_ms=now_ms
        )

    def raise_recording_gap(
        self,
        camera_id: str,
        gap_s: float,
        now_ms: int,
        db_conn: sqlite3.Connection
    ) -> dict[str, Any]:
        """Raise medium recording_gap alert."""
        message = f"Recording gap detected on {camera_id} ({gap_s:.1f}s)"
        return self.create_alert(
            db_conn=db_conn,
            level="medium",
            kind="recording_gap",
            message=message,
            target_type="camera",
            target_id=camera_id,
            now_ms=now_ms
        )
