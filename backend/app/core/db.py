import sqlite3
import threading
from collections.abc import Generator
from pathlib import Path

from app.config import config

local = threading.local()
_custom_db_path: Path | None = None

def set_db_path(path: Path | None) -> None:
    global _custom_db_path
    _custom_db_path = path
    if hasattr(local, "conn") and local.conn is not None:
        try:
            local.conn.close()
        except Exception:
            pass
        local.conn = None

def get_db_path() -> Path:
    if _custom_db_path is not None:
        return _custom_db_path
    data_dir = Path(config.paths.get("data_dir", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "mcvms.db"

def get_connection() -> sqlite3.Connection:
    if getattr(local, "conn", None) is None:
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
    started_tx = False
    if not conn.in_transaction:
        conn.execute("BEGIN")
        started_tx = True
    try:
        yield conn
        if started_tx and conn.in_transaction:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
