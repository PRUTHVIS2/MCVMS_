import sqlite3
import threading
from typing import Generator
from pathlib import Path
from app.config import config

local = threading.local()

def get_db_path() -> Path:
    data_dir = Path(config.paths.get("data_dir", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "mcvms.db"

def get_connection() -> sqlite3.Connection:
    if not hasattr(local, "conn"):
        conn = sqlite3.connect(
            get_db_path(),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        local.conn = conn
    return local.conn

def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
