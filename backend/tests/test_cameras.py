import pytest
from fastapi.testclient import TestClient

from app.core.clock import Clock
from app.core.db import get_connection
from app.core.security import get_password_hash
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    import ulid

    from app.tools.migrate import migrate
    migrate(Clock())
    
    conn = get_connection()
    conn.execute("DELETE FROM user_cameras")
    conn.execute("DELETE FROM alerts")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM calendar_exemptions")
    conn.execute("DELETE FROM registered_actions")
    conn.execute("DELETE FROM zones")
    conn.execute("DELETE FROM cameras")
    existing = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(ulid.ULID()), 'admin', get_password_hash('adminpass'), 'owner', 1, Clock().now_ms())
        )
        conn.commit()
    yield

def get_token():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "adminpass"})
    return resp.json()["access_token"]

def test_camera_crud():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create
    resp = client.post("/api/v1/cameras", json={
        "name": "cam1",
        "rtsp_url": "rtsp://secret/url",
        "features": {"vehicles": True}
    }, headers=headers)
    assert resp.status_code == 200
    cam = resp.json()
    assert cam["name"] == "cam1"
    
    # List
    resp2 = client.get("/api/v1/cameras", headers=headers)
    assert resp2.status_code == 200
    cams = resp2.json()
    assert len(cams) == 1
    
    # Verify RTSP URL is never exposed in API response
    assert "rtsp_url" not in cams[0]
    assert "rtsp_url_enc" not in cams[0]

    # Duplicate camera name returns 409
    dup_resp = client.post("/api/v1/cameras", json={
        "name": "cam1",
        "rtsp_url": "rtsp://secret/another_url"
    }, headers=headers)
    assert dup_resp.status_code == 409
    assert dup_resp.json()["detail"]["code"] == "camera_name_exists"

    # Get single camera
    cam_id = cam["id"]
    get_resp = client.get(f"/api/v1/cameras/{cam_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == cam_id
    assert "rtsp_url" not in get_resp.json()

    # Update camera
    patch_resp = client.patch(f"/api/v1/cameras/{cam_id}", json={
        "name": "cam1_renamed",
        "enabled": False
    }, headers=headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "cam1_renamed"
    assert patch_resp.json()["enabled"] is False

    # Delete camera
    del_resp = client.delete(f"/api/v1/cameras/{cam_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Verify deleted
    get_del = client.get(f"/api/v1/cameras/{cam_id}", headers=headers)
    assert get_del.status_code == 404
