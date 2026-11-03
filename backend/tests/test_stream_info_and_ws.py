import pytest
from fastapi.testclient import TestClient

from app.core.clock import Clock
from app.core.db import get_connection
from app.core.security import create_access_token, get_password_hash
from app.main import app

client = TestClient(app)

OWNER_ID = "01M6TESTOWNER000000000000"
INCHARGE_ID = "01M6TESTINCHARGE00000000"

@pytest.fixture(autouse=True)
def setup_db():
    from app.tools.migrate import migrate
    migrate(Clock())

    conn = get_connection()
    conn.execute("DELETE FROM user_cameras")
    conn.execute("DELETE FROM cameras")
    conn.execute("DELETE FROM users")

    # Seed owner
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (OWNER_ID, "admin", get_password_hash("adminpass"), "owner", 1, Clock().now_ms())
    )
    # Seed in-charge
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (INCHARGE_ID, "incharge1", get_password_hash("inchargepass"), "incharge", 1, Clock().now_ms())
    )
    conn.commit()
    yield

def get_token(user_id=OWNER_ID, role="owner"):
    return create_access_token(data={"sub": user_id, "role": role})

def test_stream_info_endpoint():
    token = get_token(OWNER_ID, "owner")
    headers = {"Authorization": f"Bearer {token}"}

    # Create camera
    create_resp = client.post("/api/v1/cameras", json={
        "name": "cam_gate",
        "rtsp_url": "rtsp://secret.stream/cam01",
        "features": {"vehicles": True, "id_check": False}
    }, headers=headers)
    assert create_resp.status_code == 200
    cam = create_resp.json()
    cam_id = cam["id"]

    # Request stream info
    info_resp = client.get(f"/api/v1/cameras/{cam_id}/stream-info", headers=headers)
    assert info_resp.status_code == 200
    info = info_resp.json()
    assert info["camera_id"] == cam_id
    assert info["name"] == "cam_gate"
    assert "rtsp" not in info["webrtc_url"]
    assert "http://localhost:8889/cam_gate/whep" == info["webrtc_url"]
    assert "http://localhost:8888/cam_gate/index.m3u8" == info["hls_url"]
    assert "rtsp_url" not in info

def test_stream_info_incharge_permission():
    admin_token = get_token(OWNER_ID, "owner")
    incharge_token = get_token(INCHARGE_ID, "incharge")

    # Create camera
    create_resp = client.post("/api/v1/cameras", json={
        "name": "cam_secure",
        "rtsp_url": "rtsp://secret.stream/cam02",
        "features": {"vehicles": True}
    }, headers={"Authorization": f"Bearer {admin_token}"})
    cam_id = create_resp.json()["id"]

    # Incharge without assignment gets 403
    resp_forbidden = client.get(
        f"/api/v1/cameras/{cam_id}/stream-info",
        headers={"Authorization": f"Bearer {incharge_token}"}
    )
    assert resp_forbidden.status_code == 403

    # Assign camera to incharge user
    conn = get_connection()
    conn.execute(
        "INSERT INTO user_cameras (user_id, camera_id) VALUES (?, ?)",
        (INCHARGE_ID, cam_id)
    )
    conn.commit()

    # Now incharge can access stream info
    resp_ok = client.get(
        f"/api/v1/cameras/{cam_id}/stream-info",
        headers={"Authorization": f"Bearer {incharge_token}"}
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["camera_id"] == cam_id

def test_websocket_subscribe():
    with client.websocket_connect("/ws") as ws:
        ws.send_text('{"type": "subscribe", "camera_ids": ["cam01"]}')
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"
        assert resp["camera_ids"] == ["cam01"]

        ws.send_text('{"type": "ping"}')
        pong = ws.receive_json()
        assert pong["type"] == "pong"

def test_rtsp_source_low_latency_env():
    import os
    from app.sources.rtsp import _set_rtsp_tcp_env
    _set_rtsp_tcp_env()
    opt = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")
    assert "timeout;2500000" in opt
    assert "nobuffer" in opt
    assert "max_delay" in opt
