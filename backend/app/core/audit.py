from app.core.db import get_connection
from app.core.clock import Clock
import json

def log_audit(user_id: str | None, action: str, target: str, detail: dict | None = None):
    conn = get_connection()
    ts = Clock().now_ms()
    detail_str = json.dumps(detail) if detail else None
    
    conn.execute(
        "INSERT INTO audit_log (ts, user_id, action, target, detail_json) VALUES (?, ?, ?, ?, ?)",
        (ts, user_id, action, target, detail_str)
    )
