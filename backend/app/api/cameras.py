import json
import logging
import sqlite3
from typing import Annotated

import cv2
import ulid
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.api.dependencies import require_admin, require_incharge
from app.core.audit import log_audit
from app.core.clock import Clock
from app.core.db import get_db
from app.core.security import decrypt_url, encrypt_url
from app.models.user import UserOut

router = APIRouter(prefix="/cameras", tags=["cameras"])
logger = logging.getLogger(__name__)


class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    features: dict = {"vehicles": True, "id_check": False}


class CameraUpdate(BaseModel):
    name: str | None = None
    rtsp_url: str | None = None
    features: dict | None = None
    enabled: bool | None = None


class CameraOut(BaseModel):
    id: str
    name: str
    enabled: bool
    features: dict
    width: int | None
    height: int | None
    fps: float | None
    status: str


class StreamInfoOut(BaseModel):
    camera_id: str
    name: str
    status: str
    webrtc_url: str
    hls_url: str
    width: int | None = None
    height: int | None = None
    fps: float | None = None


@router.get("", response_model=list[CameraOut])
def list_cameras(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_incharge)]
):
    if current_user.role == "incharge":
        if not current_user.cameras:
            return []
        placeholders = ",".join("?" * len(current_user.cameras))
        rows = db.execute(f"SELECT * FROM cameras WHERE id IN ({placeholders})", current_user.cameras).fetchall()
    else:
        rows = db.execute("SELECT * FROM cameras").fetchall()
    return [
        CameraOut(
            id=r["id"],
            name=r["name"],
            enabled=bool(r["enabled"]),
            features=json.loads(r["features_json"]),
            width=r["width"],
            height=r["height"],
            fps=r["fps"],
            status=r["status"]
        ) for r in rows
    ]


@router.get("/{cam_id}", response_model=CameraOut)
def get_camera(
    cam_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_incharge)]
):
    if current_user.role == "incharge" and cam_id not in current_user.cameras:
        raise HTTPException(status_code=403, detail="Camera access forbidden")
    row = db.execute("SELECT * FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")

    return CameraOut(
        id=row["id"],
        name=row["name"],
        enabled=bool(row["enabled"]),
        features=json.loads(row["features_json"]),
        width=row["width"],
        height=row["height"],
        fps=row["fps"],
        status=row["status"]
    )


@router.get("/{cam_id}/stream-info", response_model=StreamInfoOut)
def get_stream_info(
    cam_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_incharge)]
):
    if current_user.role == "incharge" and cam_id not in current_user.cameras:
        raise HTTPException(status_code=403, detail="Camera access forbidden")
    row = db.execute("SELECT * FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    name = row["name"]
    return StreamInfoOut(
        camera_id=row["id"],
        name=name,
        status=row["status"],
        webrtc_url=f"http://localhost:8889/{name}/whep",
        hls_url=f"http://localhost:8888/{name}/index.m3u8",
        width=row["width"],
        height=row["height"],
        fps=row["fps"]
    )


@router.post("", response_model=CameraOut)
def create_camera(
    cam: CameraCreate,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    existing = db.execute("SELECT id FROM cameras WHERE name = ?", (cam.name,)).fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"code": "camera_name_exists", "message": f"Camera '{cam.name}' already exists"}
        )

    cam_id = str(ulid.ULID())
    enc_url = encrypt_url(cam.rtsp_url)
    features_json = json.dumps(cam.features)

    db.execute(
        "INSERT INTO cameras (id, name, rtsp_url_enc, enabled, features_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cam_id, cam.name, enc_url, 1, features_json, "unknown", Clock().now_ms())
    )

    log_audit(
        user_id=current_user.id,
        action="camera_created",
        target=cam_id,
        detail={"name": cam.name}
    )

    return CameraOut(
        id=cam_id,
        name=cam.name,
        enabled=True,
        features=cam.features,
        width=None,
        height=None,
        fps=None,
        status="unknown"
    )


@router.patch("/{cam_id}", response_model=CameraOut)
def update_camera(
    cam_id: str,
    update: CameraUpdate,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT * FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")

    new_name = update.name if update.name is not None else row["name"]
    if update.name is not None and update.name != row["name"]:
        existing = db.execute("SELECT id FROM cameras WHERE name = ? AND id != ?", (update.name, cam_id)).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"code": "camera_name_exists", "message": f"Camera '{update.name}' already exists"}
            )

    new_rtsp_enc = encrypt_url(update.rtsp_url) if update.rtsp_url is not None else row["rtsp_url_enc"]
    new_features = json.dumps(update.features) if update.features is not None else row["features_json"]
    new_enabled = int(update.enabled) if update.enabled is not None else row["enabled"]

    db.execute(
        "UPDATE cameras SET name = ?, rtsp_url_enc = ?, features_json = ?, enabled = ? WHERE id = ?",
        (new_name, new_rtsp_enc, new_features, new_enabled, cam_id)
    )

    from app.pipeline.camera_runtime import reload_camera_rules
    reload_camera_rules(cam_id, db)

    log_audit(
        user_id=current_user.id,
        action="camera_updated",
        target=cam_id,
        detail={"name": new_name, "enabled": bool(new_enabled)}
    )

    updated = db.execute("SELECT * FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    return CameraOut(
        id=updated["id"],
        name=updated["name"],
        enabled=bool(updated["enabled"]),
        features=json.loads(updated["features_json"]),
        width=updated["width"],
        height=updated["height"],
        fps=updated["fps"],
        status=updated["status"]
    )


@router.delete("/{cam_id}")
def delete_camera(
    cam_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT id, name FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")

    from app.pipeline.camera_runtime import get_runtime, unregister_runtime
    rt = get_runtime(cam_id)
    if rt:
        try:
            rt.stop()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Error stopping runtime {cam_id}: {e}")
        unregister_runtime(cam_id)

    # Delete dependent relations
    zone_ids = [z["id"] for z in db.execute("SELECT id FROM zones WHERE camera_id = ?", (cam_id,)).fetchall()]
    for zid in zone_ids:
        db.execute("DELETE FROM registered_actions WHERE zone_id = ?", (zid,))
    db.execute("DELETE FROM zones WHERE camera_id = ?", (cam_id,))
    db.execute("DELETE FROM calendar_exemptions WHERE camera_id = ?", (cam_id,))
    db.execute("DELETE FROM user_cameras WHERE camera_id = ?", (cam_id,))
    db.execute("DELETE FROM alerts WHERE target_id = ? AND target_type = 'camera'", (cam_id,))
    db.execute("DELETE FROM events WHERE camera_id = ?", (cam_id,))
    db.execute("DELETE FROM cameras WHERE id = ?", (cam_id,))

    log_audit(
        user_id=current_user.id,
        action="camera_deleted",
        target=cam_id,
        detail={"name": row["name"]}
    )

    return {"status": "deleted", "id": cam_id}


@router.post("/{cam_id}/test")
def test_camera(
    cam_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT rtsp_url_enc FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")

    url = decrypt_url(row["rtsp_url_enc"])
    from app.sources.rtsp import _set_rtsp_tcp_env
    _set_rtsp_tcp_env()
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        return {"status": "failed", "reason": "Could not open stream"}

    ret, _frame = cap.read()
    if not ret:
        cap.release()
        return {"status": "failed", "reason": "Could not read frame"}

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    cap.release()

    db.execute("UPDATE cameras SET width=?, height=?, fps=?, status=? WHERE id=?", (width, height, fps, "online", cam_id))

    return {"status": "ok", "width": width, "height": height, "fps": fps}


@router.get("/{cam_id}/snapshot")
def get_snapshot(
    cam_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_incharge)]
):
    if current_user.role == "incharge" and cam_id not in current_user.cameras:
        raise HTTPException(status_code=403, detail="Camera access forbidden")
    row = db.execute("SELECT rtsp_url_enc FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")

    url = decrypt_url(row["rtsp_url_enc"])
    from app.sources.rtsp import _set_rtsp_tcp_env
    _set_rtsp_tcp_env()
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise HTTPException(status_code=503, detail="Could not open stream")

    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise HTTPException(status_code=503, detail="Could not read frame")

    _, buffer = cv2.imencode('.jpg', frame)
    return Response(content=buffer.tobytes(), media_type="image/jpeg")
