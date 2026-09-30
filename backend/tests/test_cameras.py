import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.db import get_connection
from app.core.security import get_password_hash
from app.core.clock import Clock

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    from app.tools.migrate import migrate
    import ulid
    migrate(Clock())
    
    conn = get_connection()
    conn.execute("DELETE FROM user_cameras")
    conn.execute("DELETE FROM events")
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
