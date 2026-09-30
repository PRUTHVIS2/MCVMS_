from pydantic import BaseModel
import sqlite3
from app.core.db import get_connection

class HealthStatus(BaseModel):
    status: str
    db_locked: bool
    
def get_health_status() -> HealthStatus:
    conn = get_connection()
    try:
        conn.execute("SELECT 1 FROM schema_version")
        db_locked = False
    except sqlite3.OperationalError:
        # Might be locked, but mostly this tests basic query capability
        db_locked = True
        
    return HealthStatus(
        status="ok" if not db_locked else "degraded",
        db_locked=db_locked
    )
