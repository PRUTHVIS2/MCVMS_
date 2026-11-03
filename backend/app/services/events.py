"""Events service managing event records, decisions from RuleEngine, clip requests, and actions.

docs/04_ZONES_AND_RULES.md sections 5-6, docs/08_API_AND_UI.md sections 1, 2, 5:
- Translates RuleEngine decisions ('start', 'update', 'end') into SQLite events table rows.
- Creates associated alerts via AlertService (suppressed for dry runs).
- Requests frame-accurate event clips via Clipper.
- Late-binding attribute update broadcasting ('event.updated').
- Acknowledge and false-alarm operations with role enforcement.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import ulid

from app.api.ws import manager as ws_manager
from app.core.clock import Clock
from app.recorder.clipper import Clipper, ClipRequest
from app.rules.engine import Decision
from app.rules.models import RegisteredActionSpec
from app.services.alerts import AlertService, format_rule_alert_message

logger = logging.getLogger(__name__)


class EventService:
    """Manages event persistence, clip requests, and alert triggers."""

    def __init__(
        self,
        alert_service: AlertService | None = None,
        clipper: Clipper | None = None,
        clock: Clock | None = None
    ):
        self.alert_service = alert_service or AlertService()
        self.clipper = clipper
        self.clock = clock or Clock()
        # Map: (rule_id, track_id) -> dict(event_id, started_at, rule_spec, severity)
        self.active_events: dict[tuple[str, int | None], dict[str, Any]] = {}

    def handle_decision(
        self,
        decision: Decision,
        camera_id: str,
        db_conn: sqlite3.Connection,
        camera_name: str | None = None,
        dry_run: bool = False,
        rule_spec: RegisteredActionSpec | None = None,
        source_file: Path | None = None,
        now_ms: int | None = None
    ) -> dict[str, Any]:
        """Handle a Decision emitted by RuleEngine."""
        cam_name = camera_name or camera_id
        state_key = (decision.rule_id, decision.track_id)

        if decision.kind == "start":
            event_id = str(ulid.ULID())
            severity = decision.evidence.get("severity", "medium")
            template = decision.evidence.get("template", "presence")
            zone_id = decision.evidence.get("zone_id")
            zone_name = decision.evidence.get("zone_name", "Zone")
            rule_name = decision.evidence.get("rule_name") or (rule_spec.name if rule_spec else "Rule")
            escalated = bool(decision.evidence.get("escalated", False))

            subject_json = json.dumps(decision.subject_snapshot)
            evidence_json = json.dumps(decision.evidence)

            db_conn.execute(
                """
                INSERT INTO events (
                    id, action_id, zone_id, camera_id, severity, kind, status,
                    started_at, ended_at, track_id, subject_json, confidence,
                    evidence_json, dry_run
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, decision.rule_id, zone_id, camera_id, severity, template,
                    decision.ts_ms, decision.track_id, subject_json, float(decision.confidence),
                    evidence_json, 1 if dry_run else 0
                )
            )
            db_conn.commit()

            # Record active state
            self.active_events[state_key] = {
                "event_id": event_id,
                "started_at": decision.ts_ms,
                "severity": severity,
                "rule_spec": rule_spec,
                "rule_name": rule_name,
                "zone_name": zone_name,
                "dry_run": dry_run
            }

            event_row = self.get_event_by_id(db_conn, event_id) or {}
            ws_manager.broadcast_event("event.created", event_row)

            # Trigger alert only if not dry-run
            if not dry_run:
                is_id = (rule_spec.subject.kind == "person") if rule_spec else False
                ttl_min = rule_spec.response.alert_ttl_min if rule_spec else 240
                msg = format_rule_alert_message(
                    rule_name=rule_name,
                    camera_name=cam_name,
                    zone_name=zone_name,
                    ts_ms=decision.ts_ms,
                    severity=severity,
                    escalated=escalated,
                    subject_info=decision.subject_snapshot,
                    is_id_rule=is_id
                )
                self.alert_service.create_alert(
                    db_conn=db_conn,
                    level=severity,
                    kind="rule",
                    message=msg,
                    target_type="action",
                    target_id=decision.rule_id,
                    event_id=event_id,
                    now_ms=self.clock.now_ms(),
                    alert_ttl_min=ttl_min
                )

            return event_row

        elif decision.kind == "update":
            st = self.active_events.get(state_key)
            if not st:
                return {}

            event_id = st["event_id"]
            subject_json = json.dumps(decision.subject_snapshot)
            evidence_json = json.dumps(decision.evidence)

            db_conn.execute(
                """
                UPDATE events
                SET subject_json = ?, confidence = ?, evidence_json = ?
                WHERE id = ?
                """,
                (subject_json, float(decision.confidence), evidence_json, event_id)
            )
            db_conn.commit()

            event_row = self.get_event_by_id(db_conn, event_id) or {}
            ws_manager.broadcast_event("event.updated", event_row)
            return event_row

        elif decision.kind == "end":
            st = self.active_events.pop(state_key, None)
            if not st:
                # If end without active start (e.g. instant line crossing or flush)
                return {}

            event_id = st["event_id"]
            started_at = st["started_at"]
            ended_at = decision.ts_ms
            spec = st.get("rule_spec")
            dry = st.get("dry_run", False)

            db_conn.execute(
                "UPDATE events SET ended_at = ? WHERE id = ?",
                (ended_at, event_id)
            )
            db_conn.commit()

            # Schedule / cut clip if clipper is present and not dry-run
            clip_id = None
            if self.clipper and not dry:
                pre_roll = spec.response.pre_roll_s if spec else 15.0
                hold = spec.response.hold_s if spec else 20.0
                max_clip = spec.response.max_clip_min if spec else 15.0
                severity = st.get("severity", "medium")

                req = ClipRequest(
                    kind="event",
                    camera_id=camera_id,
                    start_ts_ms=started_at,
                    end_ts_ms=ended_at,
                    pre_roll_s=pre_roll,
                    hold_s=hold,
                    max_clip_min=max_clip,
                    metadata={"event_id": event_id, "severity": severity}
                )

                try:
                    res = self.clipper.process_clip_request(
                        req,
                        source_file=source_file,
                        wait_timeout_s=1.0,
                        db_conn=db_conn
                    )
                    clip_id = res.clip_id
                    db_conn.execute(
                        "UPDATE events SET clip_id = ? WHERE id = ?",
                        (clip_id, event_id)
                    )
                    db_conn.commit()
                except Exception as e:  # noqa: BLE001
                    logger.error(f"Failed to cut clip for event {event_id}: {e}")

            event_row = self.get_event_by_id(db_conn, event_id) or {}
            ws_manager.broadcast_event("event.ended", event_row)
            return event_row

        return {}

    def get_event_by_id(self, db_conn: sqlite3.Connection, event_id: str) -> dict[str, Any] | None:
        """Fetch event by ID with parsed JSON fields."""
        row = db_conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["subject"] = json.loads(d["subject_json"])
        except (json.JSONDecodeError, TypeError):
            d["subject"] = {}
        try:
            d["evidence"] = json.loads(d["evidence_json"]) if d["evidence_json"] else {}
        except (json.JSONDecodeError, TypeError):
            d["evidence"] = {}
        return d

    def get_events(
        self,
        db_conn: sqlite3.Connection,
        camera_id: str | None = None,
        zone_id: str | None = None,
        action_id: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        from_ts: int | None = None,
        to_ts: int | None = None,
        vehicle_id: int | None = None,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """Query events with filters."""
        clauses = []
        params = []
        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)
        if zone_id:
            clauses.append("zone_id = ?")
            params.append(zone_id)
        if action_id:
            clauses.append("action_id = ?")
            params.append(action_id)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if from_ts is not None:
            clauses.append("started_at >= ?")
            params.append(from_ts)
        if to_ts is not None:
            clauses.append("started_at <= ?")
            params.append(to_ts)
        if vehicle_id is not None:
            clauses.append("vehicle_id = ?")
            params.append(vehicle_id)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM events {where_clause} ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = db_conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["subject"] = json.loads(item["subject_json"])
            except (json.JSONDecodeError, TypeError):
                item["subject"] = {}
            try:
                item["evidence"] = json.loads(item["evidence_json"]) if item["evidence_json"] else {}
            except (json.JSONDecodeError, TypeError):
                item["evidence"] = {}
            result.append(item)
        return result

    def acknowledge_event(
        self,
        event_id: str,
        user_id: str,
        now_ms: int,
        db_conn: sqlite3.Connection
    ) -> dict[str, Any]:
        """Acknowledge an event (allowed for incharge, admin, owner)."""
        row = self.get_event_by_id(db_conn, event_id)
        if not row:
            raise KeyError(f"Event {event_id} not found")

        db_conn.execute(
            "UPDATE events SET status = 'acknowledged', ack_by = ?, ack_at = ? WHERE id = ?",
            (user_id, now_ms, event_id)
        )
        db_conn.commit()

        # Also acknowledge associated alert if open
        db_conn.execute(
            "UPDATE alerts SET status = 'acknowledged', ack_by = ?, ack_at = ? WHERE event_id = ? AND status = 'open'",
            (user_id, now_ms, event_id)
        )
        db_conn.commit()

        updated = self.get_event_by_id(db_conn, event_id) or {}
        ws_manager.broadcast_event("event.updated", updated)
        return updated

    def mark_false_alarm(
        self,
        event_id: str,
        user_id: str,
        reason: str,
        now_ms: int,
        role: str,
        db_conn: sqlite3.Connection
    ) -> dict[str, Any]:
        """Mark an event as a false alarm. Requires role in ('owner', 'admin') and a non-empty reason."""
        if role not in ("owner", "admin"):
            raise PermissionError("Only owner or admin can mark false alarm")

        if not reason or not reason.strip():
            raise ValueError("Reason is required to mark false alarm")

        row = self.get_event_by_id(db_conn, event_id)
        if not row:
            raise KeyError(f"Event {event_id} not found")

        db_conn.execute(
            "UPDATE events SET status = 'false_alarm', note = ?, ack_by = ?, ack_at = ? WHERE id = ?",
            (reason.strip(), user_id, now_ms, event_id)
        )
        db_conn.commit()

        # Also dismiss any linked alert
        db_conn.execute(
            "UPDATE alerts SET status = 'dismissed', dismiss_reason = ?, ack_by = ?, ack_at = ? WHERE event_id = ?",
            (f"Event marked false alarm: {reason.strip()}", user_id, now_ms, event_id)
        )
        db_conn.commit()

        updated = self.get_event_by_id(db_conn, event_id) or {}
        ws_manager.broadcast_event("event.updated", updated)
        return updated
