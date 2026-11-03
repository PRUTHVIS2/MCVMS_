import hashlib
from pathlib import Path
from app.core.db import get_connection, get_db_path, set_db_path


def test_real_db_is_untouched_by_tests(tmp_path: Path):
    """Verify that test operations execute against tmp_path and never touch data/mcvms.db."""
    real_db = Path("data/mcvms.db")
    if not real_db.exists():
        real_db = Path("backend/data/mcvms.db")

    assert real_db.exists(), "Real database file data/mcvms.db must exist for verification"

    real_bytes_before = real_db.read_bytes()
    real_hash_before = hashlib.sha256(real_bytes_before).hexdigest()
    real_mtime_before = real_db.stat().st_mtime_ns

    # Current db path in this test must be pointing to tmp_path, not real_db
    active_db_path = get_db_path()
    assert active_db_path.resolve() != real_db.resolve()

    # Perform extensive DB writes in the test context
    conn = get_connection()
    conn.execute("CREATE TABLE IF NOT EXISTS isolation_probe (id INTEGER PRIMARY KEY, msg TEXT)")
    conn.execute("INSERT INTO isolation_probe (msg) VALUES ('probe_isolation')")
    conn.commit()

    # Verify real DB file on disk is strictly byte-for-byte identical and unchanged
    real_bytes_after = real_db.read_bytes()
    real_hash_after = hashlib.sha256(real_bytes_after).hexdigest()
    real_mtime_after = real_db.stat().st_mtime_ns

    assert real_hash_before == real_hash_after
    assert real_mtime_before == real_mtime_after

