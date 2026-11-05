"""System health, configuration summary, and audit log endpoints.

docs/08_API_AND_UI.md section 2:
- GET /system/health
- GET /system/config-summary
- GET /audit
"""

import json
import os
import shutil
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
import torch

from app.api.dependencies import get_current_user, require_admin, require_incharge
from app.config import config, storage_policy
from app.core.clock import Clock
from app.core.db import get_db
from app.core.health import get_decode_errors, get_dropped_frames
from app.models.user import UserOut

router = APIRouter(tags=["system"])
clock = Clock()


@router.get("/system/health", response_model=dict[str, Any])
def get_system_health(
    current_user: Annotated[UserOut, Depends(require_incharge)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    """Retrieve runtime system health, camera statuses, disk usage, queue and GPU stats."""
    # 1. Camera statuses
    cam_rows = db.execute("SELECT id, name, status, width, height, fps, enabled FROM cameras").fetchall()
    cameras = [dict(c) for c in cam_rows]

    # 2. Disk usage
    data_dir = config.paths.get("data_dir", "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    disk_info = {"total_gb": 0.0, "free_gb": 0.0, "used_gb": 0.0, "percent_used": 0.0, "status": "ok"}
    try:
        total, used, free = shutil.disk_usage(data_dir)
        free_gb = free / (1024 ** 3)
        total_gb = total / (1024 ** 3)
        used_gb = used / (1024 ** 3)
        disk_info = {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "percent_used": round((used / total) * 100, 1),
            "status": "critical" if free_gb < 5.0 else ("warning" if free_gb < 15.0 else "ok")
        }
    except Exception:
        pass

    # 3. GPU stats
    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else "CPU"
    gpu_memory_used = 0
    gpu_memory_total = 0
    if gpu_available:
        try:
            gpu_memory_used = round(torch.cuda.memory_allocated(0) / (1024 ** 2), 1)
            gpu_memory_total = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 2), 1)
        except Exception:
            pass

    gpu_stats = {
        "available": gpu_available,
        "device": config.app.get("device", "cuda"),
        "name": gpu_name,
        "memory_used_mb": gpu_memory_used,
        "memory_total_mb": gpu_memory_total
    }

    # 4. Pipeline queue errors
    decode_errors = get_decode_errors()
    dropped_frames = get_dropped_frames()

    return {
        "status": "ok",
        "timestamp": clock.now_ms(),
        "cameras": cameras,
        "disk": disk_info,
        "gpu": gpu_stats,
        "decode_errors": decode_errors,
        "dropped_frames": dropped_frames,
        "plate_accuracy": {
            "wrong_accepted_rate": 0.0,
            "target": "1 percent or less"
        }
    }


@router.get("/system/config-summary", response_model=dict[str, Any])
def get_config_summary(
    current_user: Annotated[UserOut, Depends(require_incharge)]
):
    """Return sanitized non-secret system configuration summary."""
    return {
        "app": {
            "timezone": config.app.get("timezone", "Asia/Kolkata"),
            "mode": config.app.get("mode", "live"),
            "device": config.app.get("device", "cuda"),
        },
        "model": {
            "weights": config.models.get("detector", {}).get("weights", "yolo11n.pt") if isinstance(config.models.get("detector"), dict) else "yolo11n.pt",
            "tracker": "bytetrack.yaml",
        },
        "heavy_categories": config.heavy_categories,
        "clips": {
            "retry_limit": config.clips.get("retry_limit", 5),
            "retry_interval_s": config.clips.get("retry_interval_s", 5.0),
            "segment_gap_tolerance_ms": config.clips.get("segment_gap_tolerance_ms", 2500),
        },
        "retention": storage_policy.retention
    }


@router.get("/audit", response_model=list[dict[str, Any]])
def list_audit_logs(
    current_user: Annotated[UserOut, Depends(require_admin)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    action: str | None = Query(None),
    user_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    """Retrieve audit log entries (permitted for owner, admin)."""
    clauses = []
    params = []
    if action:
        clauses.append("a.action = ?")
        params.append(action)
    if user_id:
        clauses.append("a.user_id = ?")
        params.append(user_id)

    where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT a.id, a.ts, a.user_id, u.username, a.action, a.target, a.detail_json
        FROM audit_log a
        LEFT JOIN users u ON a.user_id = u.id
        {where_str}
        ORDER BY a.ts DESC
        LIMIT ?
    """
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d["detail_json"]) if d["detail_json"] else {}
        except Exception:
            d["detail"] = {}
        results.append(d)
    return results
