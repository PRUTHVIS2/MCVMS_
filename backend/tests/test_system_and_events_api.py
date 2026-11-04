import os
from pathlib import Path
import sqlite3
import pytest
import ulid
from fastapi.testclient import TestClient

from app.core.clock import Clock
from app.core.db import get_connection
from app.core.security import get_password_hash, create_access_token
from app.main import app
from app.tools.migrate import migrate

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    migrate(Clock())
    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(ulid.ULID()), 'admin', get_password_hash('adminpass'), 'owner', 1, Clock().now_ms())
        )
        conn.commit()
    yield


@pytest.fixture
def auth_headers():
    conn = get_connection()
    row = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    admin_id = row["id"]
    token = create_access_token(data={"sub": admin_id, "role": "owner"})
    return {"Authorization": f"Bearer {token}"}


def test_system_health_endpoint(auth_headers):
    resp = client.get("/api/v1/system/health", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "cameras" in data
    assert "disk" in data
    assert "gpu" in data
    assert "total_gb" in data["disk"]
    assert "free_gb" in data["disk"]


def test_system_config_summary(auth_headers):
    resp = client.get("/api/v1/system/config-summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"]["timezone"] == "Asia/Kolkata"
    assert "truck" in data["heavy_categories"]
    assert "bus" in data["heavy_categories"]
    assert data["clips"]["retry_limit"] == 5


def test_audit_logs_endpoint(auth_headers):
    resp = client.get("/api/v1/audit", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "action" in data[0]
        assert "ts" in data[0]


def test_event_clip_range_request(auth_headers, tmp_path):
    conn = get_connection()
    now_ms = 1793578670000

    # Create dummy video clip
    clip_file = tmp_path / "test_event_clip.mp4"
    clip_file.write_bytes(b"0123456789" * 100) # 1000 bytes dummy mp4
    clip_id = "01M6TESTCLIP000000000000001"
    event_id = "01M6TESTEVENT0000000000001"

    # Insert clips row
    conn.execute(
        """
        INSERT OR REPLACE INTO clips (id, kind, camera_id, path, duration_s, size_bytes, sha256, status, created_at)
        VALUES (?, 'event', 'cam01', ?, 35.0, 1000, 'hash', 'ready', ?)
        """,
        (clip_id, str(clip_file), now_ms)
    )

    # Insert events row
    conn.execute(
        """
        INSERT OR REPLACE INTO events (id, action_id, zone_id, camera_id, severity, kind, started_at, clip_id, status, subject_json)
        VALUES (?, NULL, 'z1', 'cam01', 'medium', 'line_crossing', ?, ?, 'open', '{}')
        """,
        (event_id, now_ms, clip_id)
    )
    conn.commit()

    # 1. Full request
    resp_full = client.get(f"/api/v1/events/{event_id}/clip", headers=auth_headers)
    assert resp_full.status_code == 200
    assert len(resp_full.content) == 1000
    assert resp_full.headers["Accept-Ranges"] == "bytes"

    # 2. Range request
    range_headers = dict(auth_headers)
    range_headers["Range"] = "bytes=100-199"
    resp_range = client.get(f"/api/v1/events/{event_id}/clip", headers=range_headers)
    assert resp_range.status_code == 206
    assert len(resp_range.content) == 100
    assert resp_range.headers["Content-Range"] == "bytes 100-199/1000"
    assert resp_range.content == b"0123456789" * 10


def test_event_keyframes_endpoint(auth_headers, tmp_path):
    conn = get_connection()
    now_ms = 1793578670000

    clip_file = tmp_path / "clip_with_kf.mp4"
    clip_file.write_bytes(b"video")
    clip_id = "01M6TESTCLIP000000000000002"
    event_id = "01M6TESTEVENT0000000000002"

    # Create keyframe image
    kf_file = tmp_path / f"{clip_id}_key_anchor.jpg"
    kf_file.write_bytes(b"dummy_jpeg_bytes")

    conn.execute(
        """
        INSERT OR REPLACE INTO clips (id, kind, camera_id, path, duration_s, size_bytes, sha256, status, created_at)
        VALUES (?, 'event', 'cam01', ?, 35.0, 5, 'hash', 'ready', ?)
        """,
        (clip_id, str(clip_file), now_ms)
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO events (id, action_id, zone_id, camera_id, severity, kind, started_at, clip_id, status, subject_json)
        VALUES (?, NULL, 'z1', 'cam01', 'medium', 'line_crossing', ?, ?, 'open', '{}')
        """,
        (event_id, now_ms, clip_id)
    )
    conn.commit()

    resp = client.get(f"/api/v1/events/{event_id}/keyframes/anchor", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == b"dummy_jpeg_bytes"
