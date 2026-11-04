import pytest
from fastapi.testclient import TestClient

from app.core.db import get_connection
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    import ulid

    from app.core.clock import Clock
    from app.core.security import get_password_hash
    from app.tools.migrate import migrate
    migrate(Clock())
    
    conn = get_connection()
    # Bootstrap 'admin'
    existing = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(ulid.ULID()), 'admin', get_password_hash('adminpass'), 'owner', 1, Clock().now_ms())
        )
        conn.commit()
    
    yield
    # clear audit log
    get_connection().execute("DELETE FROM audit_log")
    get_connection().commit()

def test_login_success():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "adminpass"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    
    # check me
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "admin"
    assert "password" not in me_resp.json()
    assert "password_hash" not in me_resp.json()

def test_login_failure():
    # Wrong password
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect username or password"

    # Non-existent user
    resp2 = client.post("/api/v1/auth/login", data={"username": "nonexistent", "password": "any"})
    assert resp2.status_code == 401
    assert resp2.json()["detail"] == "Incorrect username or password"

    # Verify server audit log kept specific reasons without exposing them in response
    conn = get_connection()
    logs = conn.execute("SELECT * FROM audit_log WHERE action = 'login_failed' ORDER BY ts DESC LIMIT 2").fetchall()
    reasons = [log["detail_json"] for log in logs]
    assert any("user_not_found" in r for r in reasons)
    assert any("wrong_password" in r for r in reasons)

def test_rate_limit():
    for _ in range(5):
        client.post("/api/v1/auth/login", data={"username": "admin", "password": "wrong"})
    
    # 6th should be 429
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 429
    
    # clear login_attempts for other tests
    from app.api.dependencies import login_attempts
    login_attempts.clear()

def test_audit_written():
    conn = get_connection()
    count_before = conn.execute("SELECT COUNT(*) as c FROM audit_log").fetchone()["c"]
    
    # do a login
    client.post("/api/v1/auth/login", data={"username": "admin", "password": "adminpass"})
    
    count_after = conn.execute("SELECT COUNT(*) as c FROM audit_log").fetchone()["c"]
    assert count_after > count_before

def test_permissions_matrix_skeleton():
    # Admin is owner. Create an incharge user to test permission
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "adminpass"})
    token = resp.json()["access_token"]
    
    # create in-charge
    import ulid
    unique_user = "inch_" + str(ulid.ULID())
    create_resp = client.post(
        "/api/v1/users", 
        json={"username": unique_user, "password": "pwd", "role": "incharge"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert create_resp.status_code == 200
    
    # login as incharge
    inch_login = client.post("/api/v1/auth/login", data={"username": unique_user, "password": "pwd"})
    inch_token = inch_login.json()["access_token"]
    
    # try to hit /api/v1/users as incharge (should be forbidden since it's require_owner)
    fail_resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {inch_token}"})
    assert fail_resp.status_code == 403

    # In-charge can list events and alerts
    events_resp = client.get("/api/v1/events", headers={"Authorization": f"Bearer {inch_token}"})
    assert events_resp.status_code == 200

    alerts_resp = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {inch_token}"})
    assert alerts_resp.status_code == 200

    # In-charge cannot dismiss alert or mark false alarm -> 403
    dismiss_fail = client.post(
        "/api/v1/alerts/dummy_alert/dismiss",
        json={"reason": "test"},
        headers={"Authorization": f"Bearer {inch_token}"}
    )
    assert dismiss_fail.status_code == 403

    false_alarm_fail = client.post(
        "/api/v1/events/dummy_event/false-alarm",
        json={"reason": "test"},
        headers={"Authorization": f"Bearer {inch_token}"}
    )
    assert false_alarm_fail.status_code == 403
