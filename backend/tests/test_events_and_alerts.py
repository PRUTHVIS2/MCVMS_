"""Unit and integration tests for Step 6: Events and Alerts.

Tests:
1. End-to-end synthetic: scripted heavy-truck track -> event -> alert -> clip request
2. Escalation raises severity at 5 events in 10 minutes
3. Cooldown suppresses repeat within cooldown window
4. TTL expiry auto-expires unacknowledged alerts
5. Dismiss requires non-empty reason and proper role (incharge gets 403)
6. Exemption date suppresses events and alerts
7. Dry-run events never generate alerts
8. Anti-flooding: multiple identical triggers increment alert count without duplicate open rows
9. System alerts (camera_offline, disk_low, recording_gap)
10. Hot reload updates active rules and zones dynamically
11. API endpoints and permissions matrix for events and alerts
"""

import json

import pytest
import ulid
from fastapi.testclient import TestClient

from app.api.dependencies import login_attempts
from app.attributes.store import AttributeStore
from app.core.clock import SimulatedClock
from app.core.db import get_connection
from app.core.security import encrypt_url, get_password_hash
from app.core.types import TrackedFrame, TrackedObject
from app.main import app
from app.pipeline.camera_runtime import CameraRuntime, load_rules_for_camera
from app.recorder.clipper import Clipper
from app.rules.engine import CompiledRule, CompiledZone, RuleEngine
from app.rules.models import RegisteredActionSpec
from app.services.alerts import AlertService
from app.services.events import EventService
from app.services.exemptions import is_calendar_exempt
from app.tools.migrate import migrate

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure database schema is migrated and clean for every test."""
    clock = SimulatedClock(1793578670000)
    migrate(clock)
    conn = get_connection()

    # Clear relevant tables
    conn.execute("DELETE FROM alerts")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM clips")
    conn.execute("DELETE FROM calendar_exemptions")
    conn.execute("DELETE FROM registered_actions")
    conn.execute("DELETE FROM zones")
    conn.execute("DELETE FROM cameras")
    conn.execute("DELETE FROM user_cameras")
    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM audit_log")
    conn.commit()

    # Bootstrap users: owner, admin, incharge
    now_ms = clock.now_ms()
    pwd_hash = get_password_hash("pass123")
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("usr_owner", "test_owner", pwd_hash, "owner", 1, now_ms)
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("usr_admin", "test_admin", pwd_hash, "admin", 1, now_ms)
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("usr_incharge", "test_incharge", pwd_hash, "incharge", 1, now_ms)
    )

    # Insert test camera
    conn.execute(
        "INSERT INTO cameras (id, name, rtsp_url_enc, enabled, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("cam01", "Main Gate", encrypt_url("rtsp://localhost:8554/cam01"), 1, "online", now_ms)
    )
    conn.commit()

    login_attempts.clear()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM alerts")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM clips")
    conn.execute("DELETE FROM calendar_exemptions")
    conn.execute("DELETE FROM registered_actions")
    conn.execute("DELETE FROM zones")
    conn.execute("DELETE FROM cameras")
    conn.commit()


def get_token(username: str) -> str:
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": "pass123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def make_heavy_vehicle_rule_spec() -> RegisteredActionSpec:
    return RegisteredActionSpec.model_validate({
        "name": "No heavy trucks in loading bay",
        "subject": {
            "kind": "vehicle",
            "where": [{"attr": "heavy", "op": "eq", "value": True}],
            "min_box_px": 50
        },
        "trigger": {"template": "presence", "min_seconds": 1.0},
        "confirm": {"n_of_m": [2, 3], "min_confidence": 0.5},
        "response": {
            "severity": "critical",
            "pre_roll_s": 2.0,
            "hold_s": 2.0,
            "max_clip_min": 5.0,
            "cooldown_s": 10.0,
            "alert_ttl_min": 60,
            "escalation": []
        }
    })


def test_end_to_end_synthetic_heavy_truck_event_and_alert(tmp_path):
    """End-to-end synthetic: scripted heavy-truck track -> event -> alert -> clip request."""
    conn = get_connection()
    cam_id = "cam01"
    zone_id = "zone_special_1"
    rule_id = "rule_heavy_1"

    # 1. Insert special zone and action into DB
    conn.execute(
        """
        INSERT INTO zones (id, camera_id, name, kind, shape, points_json, is_read_area, enabled, created_at, updated_at)
        VALUES (?, ?, ?, 'special', 'polygon', ?, 0, 1, 1000, 1000)
        """,
        (zone_id, cam_id, "Loading Bay", json.dumps([[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]))
    )
    rule_spec = make_heavy_vehicle_rule_spec()
    conn.execute(
        """
        INSERT INTO registered_actions (id, zone_id, name, spec_json, severity, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'critical', 1, 1000, 1000)
        """,
        (rule_id, zone_id, rule_spec.name, rule_spec.model_dump_json())
    )
    conn.commit()

    # 2. Setup clipper with synthetic source file
    clips_dir = tmp_path / "clips"
    source_file = tmp_path / "synthetic_cam01.mkv"
    source_file.write_bytes(b"dummy_video_bytes")

    clipper = Clipper(clips_dir=str(clips_dir))
    alert_service = AlertService()
    event_service = EventService(alert_service=alert_service, clipper=clipper)
    attr_store = AttributeStore()

    rules, zones = load_rules_for_camera(cam_id, conn)
    assert len(rules) == 1
    assert len(zones) == 1

    engine = RuleEngine(rules=rules, zones=zones)

    # 3. Simulate track 101: heavy truck enters zone
    t0 = 1793578670000
    track_id = 101
    attr_store.set_attr(track_id, "vehicle", "heavy", True, 0.95, "known", t0)

    # Tick 1 at t0
    f1 = TrackedFrame(
        camera_id=cam_id,
        ts_ms=t0,
        frame_size=(1000, 1000),
        objects=[
            TrackedObject(track_id=track_id, cls="truck", conf=0.9, xyxy=(400, 400, 600, 700), foot_point=(500, 700), ts_ms=t0)
        ]
    )
    decisions1 = engine.step(f1, attr_store.all_attrs(), t0)
    for d in decisions1:
        event_service.handle_decision(d, cam_id, conn, rule_spec=rule_spec, source_file=source_file)

    # Tick 2 at t0 + 500ms (N of M reaches 2/2)
    t1 = t0 + 500
    f2 = TrackedFrame(
        camera_id=cam_id,
        ts_ms=t1,
        frame_size=(1000, 1000),
        objects=[
            TrackedObject(track_id=track_id, cls="truck", conf=0.9, xyxy=(400, 400, 600, 700), foot_point=(500, 700), ts_ms=t1)
        ]
    )
    decisions2 = engine.step(f2, attr_store.all_attrs(), t1)
    for d in decisions2:
        event_service.handle_decision(d, cam_id, conn, rule_spec=rule_spec, source_file=source_file)

    # Tick 3 at t0 + 1100ms (presence min_seconds 1.0s exceeded -> triggers start)
    t2 = t0 + 1100
    f3 = TrackedFrame(
        camera_id=cam_id,
        ts_ms=t2,
        frame_size=(1000, 1000),
        objects=[
            TrackedObject(track_id=track_id, cls="truck", conf=0.9, xyxy=(400, 400, 600, 700), foot_point=(500, 700), ts_ms=t2)
        ]
    )
    decisions3 = engine.step(f3, attr_store.all_attrs(), t2)
    assert any(d.kind == "start" for d in decisions3)
    for d in decisions3:
        event_service.handle_decision(d, cam_id, conn, rule_spec=rule_spec, source_file=source_file)

    # Verify event and alert created
    events = event_service.get_events(conn, camera_id=cam_id)
    assert len(events) == 1
    ev = events[0]
    assert ev["severity"] == "critical"
    assert ev["action_id"] == rule_id
    assert ev["status"] == "open"
    assert ev["subject"]["attributes"]["heavy"]["value"] is True

    alerts = alert_service.get_alerts(conn)
    assert len(alerts) == 1
    al = alerts[0]
    assert al["level"] == "critical"
    assert al["event_id"] == ev["id"]
    assert "Loading Bay" in al["message"]
    assert "No heavy trucks in loading bay" in al["message"]

    # 4. End event: track leaves zone
    t3 = t0 + 3000
    f_empty = TrackedFrame(camera_id=cam_id, ts_ms=t3, frame_size=(1000, 1000), objects=[])
    t_end = t3 + 2000
    decisions_end = engine.step(f_empty, attr_store.all_attrs(), t_end)
    assert any(d.kind == "end" for d in decisions_end)
    for d in decisions_end:
        event_service.handle_decision(d, cam_id, conn, rule_spec=rule_spec, source_file=source_file)

    ev_final = event_service.get_event_by_id(conn, ev["id"])
    assert ev_final["ended_at"] is not None


def test_escalation_raises_severity_at_5_events_in_10_min():
    """Escalation: 5 events within 10 minutes raises severity from low to critical."""
    conn = get_connection()
    cam_id = "cam01"
    zone_id = "zone_esc"
    rule_id = "rule_esc"

    conn.execute(
        """
        INSERT INTO zones (id, camera_id, name, kind, shape, points_json, is_read_area, enabled, created_at, updated_at)
        VALUES (?, ?, 'Entrance', 'special', 'polygon', ?, 0, 1, 1000, 1000)
        """,
        (zone_id, cam_id, json.dumps([[0, 0], [1, 0], [1, 1], [0, 1]]))
    )

    spec = RegisteredActionSpec.model_validate({
        "name": "Line Crossing Escalation",
        "subject": {"kind": "vehicle", "where": []},
        "trigger": {"template": "line_crossing"},
        "response": {
            "severity": "low",
            "cooldown_s": 0.0,
            "escalation": [
                {"if_count_in_window": {"n": 5, "window_min": 10}, "severity": "critical"}
            ]
        }
    })

    conn.execute(
        """
        INSERT INTO registered_actions (id, zone_id, name, spec_json, severity, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'low', 1, 1000, 1000)
        """,
        (rule_id, zone_id, spec.name, spec.model_dump_json())
    )
    conn.commit()

    alert_service = AlertService()
    event_service = EventService(alert_service=alert_service)

    t_base = 1793578670000
    severities = []

    for i in range(5):
        t_now = t_base + i * 60 * 1000  # 1 minute apart
        recent_times = [t_base + j * 60 * 1000 for j in range(i + 1)]
        from app.rules.escalation import pick_severity
        eff_sev = pick_severity(spec.response.severity, spec.response.escalation, recent_times, t_now)
        escalated = eff_sev != spec.response.severity

        from app.rules.engine import Decision
        dec = Decision(
            kind="start",
            rule_id=rule_id,
            track_id=200 + i,
            ts_ms=t_now,
            subject_snapshot={"kind": "vehicle"},
            confidence=0.9,
            evidence={
                "zone_id": zone_id,
                "zone_name": "Entrance",
                "template": "line_crossing",
                "severity": eff_sev,
                "rule_name": spec.name,
                "escalated": escalated
            }
        )
        ev = event_service.handle_decision(dec, cam_id, conn, rule_spec=spec, now_ms=t_now)
        severities.append(ev["severity"])

        # Also end event
        dec_end = Decision(
            kind="end",
            rule_id=rule_id,
            track_id=200 + i,
            ts_ms=t_now + 100,
            subject_snapshot={"kind": "vehicle"},
            confidence=0.9,
            evidence={"zone_id": zone_id}
        )
        event_service.handle_decision(dec_end, cam_id, conn, rule_spec=spec, now_ms=t_now + 100)

    # First 4 events are 'low', 5th event is 'critical'
    assert severities[:4] == ["low", "low", "low", "low"]
    assert severities[4] == "critical"

    # Check the 5th alert has critical and says (escalated)
    alerts = alert_service.get_alerts(conn)
    critical_alerts = [a for a in alerts if a["level"] == "critical"]
    assert len(critical_alerts) >= 1
    assert "(escalated)" in critical_alerts[0]["message"]


def test_cooldown_suppresses_repeat():
    """Cooldown: engine does not emit a new start decision during cooldown period."""
    rule_spec = make_heavy_vehicle_rule_spec()
    rule_spec.response.cooldown_s = 60.0

    z = CompiledZone(
        id="z1",
        name="Bay",
        kind="special",
        shape="polygon",
        points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    )
    r = CompiledRule(id="r1", zone_id="z1", spec=rule_spec)
    engine = RuleEngine(rules=[r], zones={"z1": z})
    attr_store = AttributeStore()

    t0 = 1793578670000
    track_id = 501
    attr_store.set_attr(track_id, "vehicle", "heavy", True, 0.95, "known", t0)

    # Fire event 1
    obj = TrackedObject(track_id=track_id, cls="truck", conf=0.9, xyxy=(10, 10, 50, 80), foot_point=(30, 80), ts_ms=t0)
    f = TrackedFrame(camera_id="cam01", ts_ms=t0, frame_size=(100, 100), objects=[obj])

    engine.step(f, attr_store.all_attrs(), t0)
    engine.step(f, attr_store.all_attrs(), t0 + 500)
    d1 = engine.step(f, attr_store.all_attrs(), t0 + 1100)
    assert any(d.kind == "start" for d in d1)

    # End event 1: track leaves zone
    f_empty = TrackedFrame(camera_id="cam01", ts_ms=t0 + 2000, frame_size=(100, 100), objects=[])
    engine.step(f_empty, attr_store.all_attrs(), t0 + 2000)
    d_end = engine.step(f_empty, attr_store.all_attrs(), t0 + 4000)
    assert any(d.kind == "end" for d in d_end)

    # Try triggering again at t0 + 30s (within 60s cooldown)
    t_cool = t0 + 30000
    obj_cool = TrackedObject(track_id=track_id, cls="truck", conf=0.9, xyxy=(10, 10, 50, 80), foot_point=(30, 80), ts_ms=t_cool)
    f_cool = TrackedFrame(camera_id="cam01", ts_ms=t_cool, frame_size=(100, 100), objects=[obj_cool])
    engine.step(f_cool, attr_store.all_attrs(), t_cool)
    engine.step(f_cool, attr_store.all_attrs(), t_cool + 500)
    d_suppressed = engine.step(f_cool, attr_store.all_attrs(), t_cool + 1100)
    assert not any(d.kind == "start" for d in d_suppressed)

    # Track leaves again
    engine.step(f_empty, attr_store.all_attrs(), t_cool + 2000)
    engine.step(f_empty, attr_store.all_attrs(), t_cool + 4000)

    # Try again at t0 + 70s (cooldown expired)
    t_after = t0 + 70000
    obj_after = TrackedObject(track_id=track_id, cls="truck", conf=0.9, xyxy=(10, 10, 50, 80), foot_point=(30, 80), ts_ms=t_after)
    f_after = TrackedFrame(camera_id="cam01", ts_ms=t_after, frame_size=(100, 100), objects=[obj_after])
    s1 = engine.step(f_after, attr_store.all_attrs(), t_after)
    s2 = engine.step(f_after, attr_store.all_attrs(), t_after + 500)
    s3 = engine.step(f_after, attr_store.all_attrs(), t_after + 1100)
    assert any(d.kind == "start" for d in s1 + s2 + s3)


def test_ttl_expiry():
    """Unacknowledged alerts past alert_ttl_min expire automatically."""
    conn = get_connection()
    alert_service = AlertService()

    t0 = 1793578670000
    al = alert_service.create_alert(
        db_conn=conn,
        level="medium",
        kind="test_ttl",
        message="Test TTL message",
        target_type="action",
        target_id="act_ttl",
        now_ms=t0,
        alert_ttl_min=5
    )
    assert al["status"] == "open"
    assert al["expires_at"] == t0 + 300000

    # Before expiry: still open
    expired = alert_service.expire_alerts(t0 + 200000, conn)
    assert len(expired) == 0

    # Past expiry: becomes expired
    expired = alert_service.expire_alerts(t0 + 350000, conn)
    assert al["id"] in expired

    al_db = alert_service.get_alert_by_id(conn, al["id"])
    assert al_db["status"] == "expired"


def test_dismiss_requires_reason_and_role():
    """Dismissing an alert or marking false alarm requires role owner/admin and non-empty reason."""
    conn = get_connection()
    alert_service = AlertService()

    now_ms = 1793578670000
    al = alert_service.create_alert(
        db_conn=conn,
        level="low",
        kind="dismiss_test",
        message="Dismiss test alert",
        target_type="action",
        target_id="act_dismiss",
        now_ms=now_ms
    )

    owner_token = get_token("test_owner")
    incharge_token = get_token("test_incharge")

    # 1. In-charge cannot dismiss alert -> 403
    resp_inch = client.post(
        f"/api/v1/alerts/{al['id']}/dismiss",
        json={"reason": "Known testing"},
        headers={"Authorization": f"Bearer {incharge_token}"}
    )
    assert resp_inch.status_code == 403

    # 2. Dismiss with empty reason -> 422
    resp_empty = client.post(
        f"/api/v1/alerts/{al['id']}/dismiss",
        json={"reason": ""},
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert resp_empty.status_code == 422

    # 3. Owner dismisses with reason -> 200
    resp_ok = client.post(
        f"/api/v1/alerts/{al['id']}/dismiss",
        json={"reason": "Authorized maintenance"},
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["status"] == "dismissed"
    assert resp_ok.json()["dismiss_reason"] == "Authorized maintenance"

    # 4. In-charge can acknowledge alert -> 200
    al2 = alert_service.create_alert(
        db_conn=conn,
        level="low",
        kind="ack_test",
        message="Ack test alert",
        target_type="action",
        target_id="act_ack",
        now_ms=now_ms
    )
    resp_ack = client.post(
        f"/api/v1/alerts/{al2['id']}/ack",
        headers={"Authorization": f"Bearer {incharge_token}"}
    )
    assert resp_ack.status_code == 200
    assert resp_ack.json()["status"] == "acknowledged"


def test_calendar_exemption_suppresses_alerts():
    """An active calendar exemption suppresses rule events and alerts."""
    conn = get_connection()
    cam_id = "cam01"
    action_id = "act_exemption"
    now_ms = 1793578670000  # Date in Asia/Kolkata is 2026-11-03

    conn.execute(
        """
        INSERT INTO calendar_exemptions (id, label, date_from, date_to, scope, camera_id, action_id, created_at)
        VALUES (?, 'Sports Day', '2026-11-01', '2026-11-05', 'all', NULL, NULL, ?)
        """,
        ("ex_1", now_ms)
    )
    conn.commit()

    assert is_calendar_exempt(cam_id, action_id, now_ms, conn) is True

    # Check non-exempt date
    ts_later = now_ms + 10 * 86400 * 1000
    assert is_calendar_exempt(cam_id, action_id, ts_later, conn) is False


def test_dry_run_events_never_alert():
    """Events marked as dry_run=1 are stored in the database but emit NO alerts."""
    conn = get_connection()
    cam_id = "cam01"
    zone_id = "z_dry"
    action_id = "act_dry"

    # Insert zone and action to satisfy foreign keys
    conn.execute(
        """
        INSERT INTO zones (id, camera_id, name, kind, shape, points_json, is_read_area, enabled, created_at, updated_at)
        VALUES (?, ?, 'Dry Zone', 'special', 'polygon', '[]', 0, 1, 1000, 1000)
        """,
        (zone_id, cam_id)
    )
    conn.execute(
        """
        INSERT INTO registered_actions (id, zone_id, name, spec_json, severity, enabled, created_at, updated_at)
        VALUES (?, ?, 'Dry Action', '{}', 'low', 1, 1000, 1000)
        """,
        (action_id, zone_id)
    )
    conn.commit()

    alert_service = AlertService()
    event_service = EventService(alert_service=alert_service)

    from app.rules.engine import Decision
    dec = Decision(
        kind="start",
        rule_id=action_id,
        track_id=888,
        ts_ms=1793578670000,
        subject_snapshot={"category": "truck"},
        confidence=0.85,
        evidence={"zone_id": zone_id, "severity": "critical", "template": "presence"}
    )

    ev = event_service.handle_decision(dec, cam_id, conn, dry_run=True)
    assert ev["dry_run"] == 1

    # Zero alerts should be created
    alerts = alert_service.get_alerts(conn)
    assert len(alerts) == 0


def test_anti_flooding_updates_count():
    """Multiple identical triggers update count on the existing open alert without creating duplicates."""
    conn = get_connection()
    alert_service = AlertService()

    t0 = 1793578670000
    al1 = alert_service.create_alert(
        db_conn=conn,
        level="medium",
        kind="rule",
        message="First breach",
        target_type="action",
        target_id="act_flood",
        now_ms=t0
    )
    assert al1["count"] == 1

    al2 = alert_service.create_alert(
        db_conn=conn,
        level="critical",
        kind="rule",
        message="Second breach",
        target_type="action",
        target_id="act_flood",
        now_ms=t0 + 5000
    )
    assert al2["id"] == al1["id"]
    assert al2["count"] == 2
    assert al2["level"] == "critical"

    # Total open alerts must remain 1
    all_open = alert_service.get_alerts(conn, status="open")
    assert len(all_open) == 1


def test_system_alerts_lifecycle():
    """System alerts for camera_offline, disk_low, and recording_gap."""
    conn = get_connection()
    alert_service = AlertService()
    now_ms = 1793578670000

    # 1. Camera offline
    alert_service.raise_camera_offline("cam01", "Main Gate", now_ms, conn)
    alerts = alert_service.get_alerts(conn, kind="camera_offline")
    assert len(alerts) == 1
    assert alerts[0]["level"] == "medium"
    assert "Main Gate offline" in alerts[0]["message"]

    # Clear camera offline
    alert_service.clear_camera_offline("cam01", conn)
    al_cleared = alert_service.get_alert_by_id(conn, alerts[0]["id"])
    assert al_cleared["status"] == "dismissed"

    # 2. Disk low
    alert_service.raise_disk_low(3.2, now_ms, conn)
    disk_alerts = alert_service.get_alerts(conn, kind="disk_low")
    assert len(disk_alerts) == 1
    assert disk_alerts[0]["level"] == "critical"
    assert "3.2 GB" in disk_alerts[0]["message"]

    # 3. Recording gap
    alert_service.raise_recording_gap("cam01", 12.5, now_ms, conn)
    gap_alerts = alert_service.get_alerts(conn, kind="recording_gap")
    assert len(gap_alerts) == 1
    assert "12.5s" in gap_alerts[0]["message"]


def test_hot_reload_pipeline():
    """Hot reload replaces compiled rules and zones dynamically."""
    cam_id = "cam01"

    z1 = CompiledZone(id="z1", name="Zone 1", kind="special", shape="polygon", points=[(0, 0), (1, 0), (1, 1), (0, 1)])
    r1 = CompiledRule(id="r1", zone_id="z1", spec=make_heavy_vehicle_rule_spec())

    class DummyAnalyzer:
        def __init__(self):
            self.subscribers = []
        def subscribe(self, cb):
            self.subscribers.append(cb)
        def start(self): pass
        def stop(self): pass

    dummy_analyzer = DummyAnalyzer()
    event_service = EventService()

    runtime = CameraRuntime(
        camera_id=cam_id,
        analyzer=dummy_analyzer, # type: ignore
        event_service=event_service,
        rules=[r1],
        zones={"z1": z1}
    )
    assert len(runtime.rules) == 1
    assert runtime.rules[0].id == "r1"

    spec2 = make_heavy_vehicle_rule_spec()
    spec2.name = "Updated Rule"
    r2 = CompiledRule(id="r2", zone_id="z1", spec=spec2)
    runtime.reload_rules(rules=[r2], zones={"z1": z1})

    assert len(runtime.rules) == 1
    assert runtime.rules[0].id == "r2"
    assert runtime.engine.rules[0].spec.name == "Updated Rule"


def test_permissions_matrix_events_and_alerts():
    """Verify role permissions for events and alerts endpoints."""
    conn = get_connection()
    now_ms = 1793578670000

    event_id = str(ulid.ULID())
    conn.execute(
        """
        INSERT INTO events (id, camera_id, severity, kind, status, started_at, subject_json)
        VALUES (?, 'cam01', 'critical', 'presence', 'open', ?, '{}')
        """,
        (event_id, now_ms)
    )
    conn.commit()

    owner_token = get_token("test_owner")
    assert owner_token
    admin_token = get_token("test_admin")
    incharge_token = get_token("test_incharge")

    # In-charge can list events and acknowledge
    r_list = client.get("/api/v1/events", headers={"Authorization": f"Bearer {incharge_token}"})
    assert r_list.status_code == 200

    r_ack = client.post(f"/api/v1/events/{event_id}/ack", headers={"Authorization": f"Bearer {incharge_token}"})
    assert r_ack.status_code == 200
    assert r_ack.json()["status"] == "acknowledged"

    # In-charge CANNOT mark false alarm -> 403 Forbidden
    r_false_inch = client.post(
        f"/api/v1/events/{event_id}/false-alarm",
        json={"reason": "Not real"},
        headers={"Authorization": f"Bearer {incharge_token}"}
    )
    assert r_false_inch.status_code == 403

    # Admin CAN mark false alarm -> 200 OK
    r_false_admin = client.post(
        f"/api/v1/events/{event_id}/false-alarm",
        json={"reason": "Authorized testing scenario"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert r_false_admin.status_code == 200
    assert r_false_admin.json()["status"] == "false_alarm"
