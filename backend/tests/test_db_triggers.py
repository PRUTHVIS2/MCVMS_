import pytest
import sqlite3
from app.core.db import get_connection

@pytest.fixture(autouse=True)
def clean_db():
    conn = get_connection()
    # Migration is already run via the app startup or can be run manually here if not
    from app.tools.migrate import migrate
    from app.core.clock import Clock
    migrate(Clock())
    
    # We will clean the tables before each test
    conn.execute("DELETE FROM registered_actions")
    conn.execute("DELETE FROM zones")
    conn.execute("DELETE FROM cameras")
    conn.commit()

def test_trigger_registered_action_needs_special_zone():
    conn = get_connection()
    conn.execute("INSERT INTO cameras (id, name, rtsp_url_enc, created_at) VALUES ('c1', 'cam1', 'enc', 0)")
    # Insert normal zone
    conn.execute("INSERT INTO zones (id, camera_id, name, kind, shape, points_json, created_at, updated_at) VALUES ('z1', 'c1', 'zone1', 'normal', 'polygon', '[]', 0, 0)")
    conn.commit()
    
    with pytest.raises(sqlite3.IntegrityError, match="registered actions require a special zone"):
        conn.execute("INSERT INTO registered_actions (id, zone_id, name, spec_json, severity, created_at, updated_at) VALUES ('a1', 'z1', 'act1', '{}', 'low', 0, 0)")

def test_trigger_downgrade_zone_with_actions():
    conn = get_connection()
    conn.execute("INSERT INTO cameras (id, name, rtsp_url_enc, created_at) VALUES ('c1', 'cam1', 'enc', 0)")
    # Insert special zone
    conn.execute("INSERT INTO zones (id, camera_id, name, kind, shape, points_json, created_at, updated_at) VALUES ('z1', 'c1', 'zone1', 'special', 'polygon', '[]', 0, 0)")
    
    # Insert action
    conn.execute("INSERT INTO registered_actions (id, zone_id, name, spec_json, severity, created_at, updated_at) VALUES ('a1', 'z1', 'act1', '{}', 'low', 0, 0)")
    conn.commit()
    
    # Try downgrading to normal
    with pytest.raises(sqlite3.IntegrityError, match="zone still has registered actions"):
        conn.execute("UPDATE zones SET kind = 'normal' WHERE id = 'z1'")

    # But we can update shape
    conn.execute("UPDATE zones SET shape = 'polygon' WHERE id = 'z1'")
    conn.commit()
