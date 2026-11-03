"""Tests for Step 7: Camera, zone and rule management API.

Tests:
1. Geometry validation: valid/invalid polygon (3..20 points, non-self-intersecting) and line (2 points).
2. Normal-zone gating: POST /zones/{id}/actions returns 422 with code 'zone_not_special'.
3. Zone downgrade protection: changing special zone with actions to normal returns 409.
4. Spec validation: unknown attribute (422), unknown operator (422), subject-attribute mismatch (422).
5. Schedule and date validation: invalid date (422), inverted dates (422), invalid time (422).
6. Rule-templates endpoint: presets including 'heavy_vehicle' and 'any_vehicle' (where: []).
7. Calendar exemptions CRUD with date validation and audit logging.
8. Permissions matrix: Admin/Owner allowed, In-charge forbidden (403).
9. Audit rows logged for all mutations.
10. Runtime hot-reload verified.
"""


import pytest
import ulid
from fastapi.testclient import TestClient

from app.core.clock import Clock
from app.core.db import get_connection
from app.core.security import encrypt_url, get_password_hash
from app.main import app
from app.pipeline.camera_runtime import (
    CameraRuntime,
    register_runtime,
    unregister_runtime,
)
from app.services.events import EventService
from app.tools.migrate import migrate

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    from app.api.dependencies import login_attempts
    login_attempts.clear()

    migrate(Clock())
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE username <> 'admin'")
    conn.execute("DELETE FROM calendar_exemptions")
    conn.execute("DELETE FROM registered_actions")
    conn.execute("DELETE FROM zones")
    conn.execute("DELETE FROM cameras")
    conn.execute("DELETE FROM audit_log")

    # Bootstrap owner 'admin'
    existing = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(ulid.ULID()), "admin", get_password_hash("adminpass"), "owner", 1, Clock().now_ms())
        )
    conn.commit()
    yield
    # Cleanup after test so DB is left clean
    conn = get_connection()
    conn.execute("DELETE FROM calendar_exemptions")
    conn.execute("DELETE FROM registered_actions")
    conn.execute("DELETE FROM zones")
    conn.execute("DELETE FROM cameras")
    conn.commit()


def get_token(username: str = "admin", password: str = "adminpass") -> str:
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def create_incharge_user(username: str = "incharge_user") -> str:
    conn = get_connection()
    uid = str(ulid.ULID())
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (uid, username, get_password_hash("inchpass"), "incharge", 1, Clock().now_ms())
    )
    conn.commit()
    return get_token(username, "inchpass")


def create_test_camera(name: str = "Cam 1") -> str:
    conn = get_connection()
    cam_id = f"cam_{ulid.ULID()}"
    conn.execute(
        """
        INSERT INTO cameras (id, name, rtsp_url_enc, enabled, features_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (cam_id, name, encrypt_url("rtsp://localhost:8554/test"), 1, '{"vehicles":true,"id_check":false}', "online", Clock().now_ms())
    )
    conn.commit()
    return cam_id


# =========================================================================
# 1. ZONE VALIDATION & CRUD
# =========================================================================

def test_zone_geometry_validation():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    cam_id = create_test_camera("Cam Test Zone")

    # Bad: Polygon with < 3 points
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Too few points",
            "kind": "special",
            "shape": "polygon",
            "points": [[0.1, 0.1], [0.5, 0.5]]
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "between 3 and 20 points" in resp.text

    # Bad: Polygon with > 20 points
    lots_of_pts = [[0.1 * (i % 5), 0.1 * (i % 5)] for i in range(21)]
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Too many points",
            "kind": "special",
            "shape": "polygon",
            "points": lots_of_pts
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "between 3 and 20 points" in resp.text

    # Bad: Self-intersecting polygon (bowtie)
    bowtie = [[0.0, 0.0], [1.0, 1.0], [0.0, 1.0], [1.0, 0.0]]
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Self intersecting",
            "kind": "special",
            "shape": "polygon",
            "points": bowtie
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "Invalid polygon geometry" in resp.text

    # Good: Valid 4-point polygon
    good_poly = [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8], [0.1, 0.8]]
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Valid Special Polygon",
            "kind": "special",
            "shape": "polygon",
            "points": good_poly
        },
        headers=headers
    )
    assert resp.status_code == 201
    zone_data = resp.json()
    assert zone_data["name"] == "Valid Special Polygon"
    assert zone_data["kind"] == "special"

    # Bad: Line with 3 points
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Bad line",
            "kind": "normal",
            "shape": "line",
            "points": [[0.1, 0.1], [0.5, 0.5], [0.9, 0.9]]
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "Line must have exactly 2 points" in resp.text

    # Good: Valid Line
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Valid Normal Line",
            "kind": "normal",
            "shape": "line",
            "points": [[0.1, 0.5], [0.9, 0.5]],
            "direction": "in"
        },
        headers=headers
    )
    assert resp.status_code == 201
    assert resp.json()["shape"] == "line"
    assert resp.json()["direction"] == "in"


# =========================================================================
# 2. NORMAL ZONE ACTION GATING (422 zone_not_special)
# =========================================================================

def test_normal_zone_action_rejection():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    cam_id = create_test_camera("Cam Gating")

    # Create normal zone
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Normal Zone",
            "kind": "normal",
            "shape": "polygon",
            "points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
        },
        headers=headers
    )
    assert resp.status_code == 201
    normal_zone_id = resp.json()["id"]

    # Try creating registered action on normal zone -> Expect 422 zone_not_special
    action_payload = {
        "name": "No heavy trucks in normal zone",
        "subject": {
            "kind": "vehicle",
            "where": [{"attr": "heavy", "op": "eq", "value": True}]
        },
        "trigger": {
            "template": "presence",
            "min_seconds": 2.0
        },
        "response": {
            "severity": "critical"
        }
    }
    resp = client.post(
        f"/api/v1/zones/{normal_zone_id}/actions",
        json=action_payload,
        headers=headers
    )
    assert resp.status_code == 422
    err = resp.json()
    assert err["detail"]["code"] == "zone_not_special"
    assert "special zone" in err["detail"]["message"].lower()


# =========================================================================
# 3. SPECIAL ZONE WITH ACTIONS -> 409 ON DOWNGRADE
# =========================================================================

def test_zone_downgrade_conflict():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    cam_id = create_test_camera("Cam Downgrade")

    # Create special zone
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Special Zone",
            "kind": "special",
            "shape": "polygon",
            "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        },
        headers=headers
    )
    assert resp.status_code == 201
    special_zone_id = resp.json()["id"]

    # Add action
    action_payload = {
        "name": "Heavy truck rule",
        "subject": {
            "kind": "vehicle",
            "where": [{"attr": "heavy", "op": "eq", "value": True}]
        },
        "trigger": {
            "template": "presence",
            "min_seconds": 2.0
        },
        "response": {
            "severity": "critical"
        }
    }
    resp = client.post(f"/api/v1/zones/{special_zone_id}/actions", json=action_payload, headers=headers)
    assert resp.status_code == 201

    # Attempt to downgrade special zone to normal -> Expect 409 Conflict
    resp = client.patch(
        f"/api/v1/zones/{special_zone_id}",
        json={"kind": "normal"},
        headers=headers
    )
    assert resp.status_code == 409
    err = resp.json()
    assert err["detail"]["code"] == "zone_has_actions"
    assert "cannot downgrade" in err["detail"]["message"].lower()

    # Changing shape when actions exist is allowed but returns a warning
    resp = client.patch(
        f"/api/v1/zones/{special_zone_id}",
        json={"points": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]},
        headers=headers
    )
    assert resp.status_code == 200
    assert "dry run is recommended" in resp.json()["warning"].lower()


# =========================================================================
# 4. TEMPLATE, ATTRIBUTE, OPERATOR & DATE VALIDATION (422)
# =========================================================================

def test_action_spec_validation_rules():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    cam_id = create_test_camera("Cam Spec Validation")

    # Create polygon zone
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Poly Zone",
            "kind": "special",
            "shape": "polygon",
            "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        },
        headers=headers
    )
    poly_zone_id = resp.json()["id"]

    # 1. Incompatible template: line_crossing on polygon zone -> 422
    resp = client.post(
        f"/api/v1/zones/{poly_zone_id}/actions",
        json={
            "name": "Bad line crossing on poly",
            "subject": {"kind": "vehicle", "where": []},
            "trigger": {"template": "line_crossing"},
            "response": {"severity": "low"}
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "requires a 'line' zone" in resp.text

    # 2. Unknown attribute: "flying_speed" -> 422
    resp = client.post(
        f"/api/v1/zones/{poly_zone_id}/actions",
        json={
            "name": "Bad attribute rule",
            "subject": {
                "kind": "vehicle",
                "where": [{"attr": "flying_speed", "op": "eq", "value": 10}]
            },
            "trigger": {"template": "presence", "min_seconds": 1.0},
            "response": {"severity": "medium"}
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "Unknown attribute 'flying_speed'" in resp.text

    # 3. Unknown operator: "matches_regex" -> 422
    resp = client.post(
        f"/api/v1/zones/{poly_zone_id}/actions",
        json={
            "name": "Bad operator rule",
            "subject": {
                "kind": "vehicle",
                "where": [{"attr": "plate", "op": "matches_regex", "value": ".*"}]
            },
            "trigger": {"template": "presence", "min_seconds": 1.0},
            "response": {"severity": "medium"}
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "Unknown operator 'matches_regex'" in resp.text

    # 4. Attribute / subject mismatch: "id_state" on vehicle -> 422
    resp = client.post(
        f"/api/v1/zones/{poly_zone_id}/actions",
        json={
            "name": "Subject mismatch rule",
            "subject": {
                "kind": "vehicle",
                "where": [{"attr": "id_state", "op": "eq", "value": "wearing"}]
            },
            "trigger": {"template": "presence", "min_seconds": 1.0},
            "response": {"severity": "medium"}
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "not applicable to subject kind 'vehicle'" in resp.text

    # 5. Invalid date format: "2026/13/45" -> 422
    resp = client.post(
        f"/api/v1/zones/{poly_zone_id}/actions",
        json={
            "name": "Invalid date rule",
            "subject": {"kind": "vehicle", "where": []},
            "trigger": {"template": "presence", "min_seconds": 1.0},
            "valid": {"from_date": "2026/13/45"},
            "response": {"severity": "medium"}
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "YYYY-MM-DD" in resp.text

    # 6. Inverted date range: from_date > until_date -> 422
    resp = client.post(
        f"/api/v1/zones/{poly_zone_id}/actions",
        json={
            "name": "Inverted dates rule",
            "subject": {"kind": "vehicle", "where": []},
            "trigger": {"template": "presence", "min_seconds": 1.0},
            "valid": {"from_date": "2026-10-15", "until_date": "2026-10-01"},
            "response": {"severity": "medium"}
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "cannot be after until_date" in resp.text

    # 7. Invalid schedule day: "funday" -> 422
    resp = client.post(
        f"/api/v1/zones/{poly_zone_id}/actions",
        json={
            "name": "Invalid schedule day rule",
            "subject": {"kind": "vehicle", "where": []},
            "trigger": {"template": "presence", "min_seconds": 1.0},
            "schedule": {"days": ["mon", "funday"]},
            "response": {"severity": "medium"}
        },
        headers=headers
    )
    assert resp.status_code == 422
    assert "Invalid day 'funday'" in resp.text

    # 8. Valid "any vehicle" rule (where: []) -> Success 201
    resp = client.post(
        f"/api/v1/zones/{poly_zone_id}/actions",
        json={
            "name": "Any vehicle rule",
            "subject": {"kind": "vehicle", "where": []},
            "trigger": {"template": "presence", "min_seconds": 0.0},
            "response": {"severity": "medium"}
        },
        headers=headers
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Any vehicle rule"


# =========================================================================
# 5. RULE TEMPLATES & PRESETS ENDPOINT
# =========================================================================

def test_rule_templates_and_presets():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/rule-templates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "templates" in data
    assert "catalogue" in data
    assert "operators" in data
    assert "presets" in data

    # Check that presets include both heavy vehicle and any vehicle
    presets = data["presets"]
    assert "heavy_vehicle" in presets
    assert "any_vehicle" in presets
    assert presets["any_vehicle"]["subject"]["where"] == []

    # Check catalogue has vehicle and person
    assert "vehicle" in data["catalogue"]
    assert "person" in data["catalogue"]


# =========================================================================
# 6. CALENDAR EXEMPTIONS CRUD & VALIDATION
# =========================================================================

def test_calendar_exemptions_crud():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    cam_id = create_test_camera("Cam Calendar")

    # Inverted dates -> 422
    resp = client.post(
        "/api/v1/calendar",
        json={
            "label": "Bad exemption",
            "date_from": "2026-12-25",
            "date_to": "2026-12-20",
            "scope": "all"
        },
        headers=headers
    )
    assert resp.status_code == 422

    # Valid exemption
    resp = client.post(
        "/api/v1/calendar",
        json={
            "label": "Winter Break",
            "date_from": "2026-12-20",
            "date_to": "2026-12-31",
            "scope": "camera",
            "camera_id": cam_id
        },
        headers=headers
    )
    assert resp.status_code == 201
    ex_id = resp.json()["id"]

    # List
    list_resp = client.get("/api/v1/calendar", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["label"] == "Winter Break"

    # Delete
    del_resp = client.delete(f"/api/v1/calendar/{ex_id}", headers=headers)
    assert del_resp.status_code == 200

    # Verify deleted
    list_resp2 = client.get("/api/v1/calendar", headers=headers)
    assert len(list_resp2.json()) == 0


# =========================================================================
# 7. PERMISSIONS MATRIX (In-charge gets 403 Forbidden)
# =========================================================================

def test_incharge_forbidden_on_zones_actions_calendar():
    inch_token = create_incharge_user("inch_test_user")
    inch_headers = {"Authorization": f"Bearer {inch_token}"}
    cam_id = create_test_camera("Cam Perms")

    # 1. Cannot list or create zones
    resp = client.get(f"/api/v1/cameras/{cam_id}/zones", headers=inch_headers)
    assert resp.status_code == 403

    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Zone",
            "kind": "special",
            "shape": "polygon",
            "points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
        },
        headers=inch_headers
    )
    assert resp.status_code == 403

    # 2. Cannot create actions
    resp = client.post(
        "/api/v1/zones/dummy_zone/actions",
        json={
            "name": "Action",
            "subject": {"kind": "vehicle", "where": []},
            "trigger": {"template": "presence"},
            "response": {"severity": "low"}
        },
        headers=inch_headers
    )
    assert resp.status_code == 403

    # 3. Cannot manage calendar
    resp = client.post(
        "/api/v1/calendar",
        json={
            "label": "Holiday",
            "date_from": "2026-10-10",
            "date_to": "2026-10-11",
            "scope": "all"
        },
        headers=inch_headers
    )
    assert resp.status_code == 403

    resp = client.delete("/api/v1/calendar/dummy_id", headers=inch_headers)
    assert resp.status_code == 403


# =========================================================================
# 8. AUDIT LOGGING VERIFICATION
# =========================================================================

def test_audit_logging_for_zones_and_actions():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    cam_id = create_test_camera("Cam Audit")

    conn = get_connection()
    audit_count_before = conn.execute("SELECT COUNT(*) as c FROM audit_log").fetchone()["c"]

    # 1. Create Zone
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "Audit Special Zone",
            "kind": "special",
            "shape": "polygon",
            "points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
        },
        headers=headers
    )
    assert resp.status_code == 201
    zone_id = resp.json()["id"]

    # 2. Create Action
    resp = client.post(
        f"/api/v1/zones/{zone_id}/actions",
        json={
            "name": "Audit Action",
            "subject": {"kind": "vehicle", "where": []},
            "trigger": {"template": "presence", "min_seconds": 1.0},
            "response": {"severity": "medium"}
        },
        headers=headers
    )
    assert resp.status_code == 201
    action_id = resp.json()["id"]

    # 3. Update Action
    client.patch(
        f"/api/v1/actions/{action_id}",
        json={"name": "Audit Action Updated"},
        headers=headers
    )

    # 4. Delete Zone (cascades action)
    client.delete(f"/api/v1/zones/{zone_id}", headers=headers)

    audit_rows = conn.execute("SELECT action, target FROM audit_log ORDER BY id ASC").fetchall()
    assert len(audit_rows) > audit_count_before
    actions_logged = [r["action"] for r in audit_rows]

    assert "zone_created" in actions_logged
    assert "action_created" in actions_logged
    assert "action_updated" in actions_logged
    assert "zone_deleted" in actions_logged


# =========================================================================
# 9. RUNTIME HOT-RELOAD VERIFICATION
# =========================================================================

def test_hot_reload_into_active_runtime():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    cam_id = create_test_camera("Cam HotReload")

    # Mock an active CameraRuntime
    class MockAnalyzer:
        def subscribe(self, cb):
            pass
        def start(self):
            pass
        def stop(self):
            pass

    runtime = CameraRuntime(
        camera_id=cam_id,
        analyzer=MockAnalyzer(),
        event_service=EventService()
    )
    register_runtime(runtime)

    try:
        assert len(runtime.rules) == 0
        assert len(runtime.zones) == 0

        # Create special zone via API
        resp = client.post(
            f"/api/v1/cameras/{cam_id}/zones",
            json={
                "name": "HotReload Zone",
                "kind": "special",
                "shape": "polygon",
                "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
            },
            headers=headers
        )
        assert resp.status_code == 201
        zone_id = resp.json()["id"]

        # Runtime should have hot-reloaded the zone
        assert len(runtime.zones) == 1
        assert zone_id in runtime.zones

        # Add registered action
        resp = client.post(
            f"/api/v1/zones/{zone_id}/actions",
            json={
                "name": "HotReload Rule",
                "subject": {"kind": "vehicle", "where": []},
                "trigger": {"template": "presence", "min_seconds": 0.0},
                "response": {"severity": "critical"}
            },
            headers=headers
        )
        assert resp.status_code == 201

        # Runtime should have hot-reloaded the rule
        assert len(runtime.rules) == 1
        assert runtime.rules[0].spec.name == "HotReload Rule"
    finally:
        unregister_runtime(cam_id)


# =========================================================================
# 10. DRY RUN ENDPOINT & LATENCY MEASUREMENT TOOL
# =========================================================================

def test_dry_run_action(tmp_path):
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    cam_id = create_test_camera("Cam DryRun")

    # Create special zone & action
    resp = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={
            "name": "DryRun Special Zone",
            "kind": "special",
            "shape": "polygon",
            "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        },
        headers=headers
    )
    zone_id = resp.json()["id"]

    resp = client.post(
        f"/api/v1/zones/{zone_id}/actions",
        json={
            "name": "DryRun Rule",
            "subject": {"kind": "vehicle", "where": []},
            "trigger": {"template": "presence", "min_seconds": 0.0},
            "response": {"severity": "critical"}
        },
        headers=headers
    )
    action_id = resp.json()["id"]

    # 1. Non-existent clip -> 404
    resp = client.post(
        f"/api/v1/actions/{action_id}/dry-run",
        json={"clip_path": "non_existent_clip.mp4"},
        headers=headers
    )
    assert resp.status_code == 404

    # 2. Existing video clip
    import cv2
    import numpy as np

    clip_file = tmp_path / "test_dryrun.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(clip_file), fourcc, 10, (320, 240))
    for _ in range(5):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        out.write(frame)
    out.release()

    conn = get_connection()
    events_before = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
    alerts_before = conn.execute("SELECT COUNT(*) as c FROM alerts").fetchone()["c"]

    resp = client.post(
        f"/api/v1/actions/{action_id}/dry-run",
        json={"clip_path": str(clip_file), "max_frames": 5},
        headers=headers
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["action_id"] == action_id
    assert res_data["total_frames_processed"] == 5

    # Invariant: Dry run NEVER writes real events or alerts
    events_after = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
    alerts_after = conn.execute("SELECT COUNT(*) as c FROM alerts").fetchone()["c"]
    assert events_after == events_before
    assert alerts_after == alerts_before


def test_measure_latency_tool():
    from app.tools.measure_latency import fetch_latencies, print_stats

    conn = get_connection()
    cam_id = create_test_camera("Cam Latency")

    # Insert a dummy event and alert
    now = Clock().now_ms()
    event_id = f"ev_{ulid.ULID()}"
    alert_id = f"al_{ulid.ULID()}"

    conn.execute(
        """
        INSERT INTO events (id, camera_id, severity, kind, status, started_at, subject_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, cam_id, "critical", "presence", "open", now - 350, "{}")
    )
    conn.execute(
        """
        INSERT INTO alerts (id, level, kind, message, event_id, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (alert_id, "critical", "presence", "Test alert", event_id, now, "open")
    )
    conn.commit()

    records = fetch_latencies(camera_id=cam_id)
    assert len(records) >= 1
    matched = next((r for r in records if r["alert_id"] == alert_id), None)
    assert matched is not None
    assert matched["latency_ms"] == 350

    # Ensure print_stats runs without error
    print_stats(records, target_ms=2000.0)

