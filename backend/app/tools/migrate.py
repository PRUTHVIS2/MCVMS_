import os
import sqlite3
from pathlib import Path
from app.core.db import get_connection
from app.core.clock import Clock

def migrate(clock: Clock):
    conn = get_connection()
    
    # Check if schema_version exists
    try:
        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        current_version = row["v"] if row and row["v"] is not None else 0
    except sqlite3.OperationalError:
        current_version = 0

    migrations_dir = Path(__file__).resolve().parent.parent.parent / "migrations"
    
    if not migrations_dir.exists():
        print(f"Migrations directory not found at {migrations_dir}")
        return

    files = sorted([f for f in migrations_dir.iterdir() if f.name.endswith(".sql")])
    
    for file in files:
        version_str = file.name.split("_")[0]
        try:
            version = int(version_str)
        except ValueError:
            continue
            
        if version > current_version:
            print(f"Applying migration {file.name}...")
            with open(file, "r") as f:
                sql = f.read()
            
            conn.execute("BEGIN")
            try:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)", 
                    (version, clock.now_ms())
                )
                conn.commit()
                print(f"Migration {version} applied successfully.")
            except Exception as e:
                conn.rollback()
                print(f"Failed to apply migration {file.name}: {e}")
                raise

if __name__ == "__main__":
    import sqlite3
    migrate(Clock())
