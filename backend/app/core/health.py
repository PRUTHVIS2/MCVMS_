import sqlite3
from typing import Dict
from pydantic import BaseModel

from app.core.db import get_connection

_decode_error_counts: Dict[str, int] = {}
_dropped_frame_counts: Dict[str, int] = {}


def record_decode_error(camera_id: str) -> None:
    """Record a frame decoding error for a specific camera."""
    _decode_error_counts[camera_id] = _decode_error_counts.get(camera_id, 0) + 1


def get_decode_errors() -> Dict[str, int]:
    """Retrieve mapping of camera_id to decode error counts."""
    return dict(_decode_error_counts)


def reset_decode_errors() -> None:
    """Reset decode error counts (e.g. for testing)."""
    _decode_error_counts.clear()


def record_dropped_frame(camera_id: str, count: int = 1) -> None:
    """Record dropped frames for a specific camera when analyzer falls behind."""
    _dropped_frame_counts[camera_id] = _dropped_frame_counts.get(camera_id, 0) + count


def get_dropped_frames() -> Dict[str, int]:
    """Retrieve mapping of camera_id to dropped frame counts."""
    return dict(_dropped_frame_counts)


def reset_dropped_frames() -> None:
    """Reset dropped frame counts (e.g. for testing)."""
    _dropped_frame_counts.clear()


class HealthStatus(BaseModel):
    status: str
    db_locked: bool
    decode_errors: Dict[str, int] = {}
    dropped_frames: Dict[str, int] = {}


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
        db_locked=db_locked,
        decode_errors=get_decode_errors(),
        dropped_frames=get_dropped_frames(),
    )
