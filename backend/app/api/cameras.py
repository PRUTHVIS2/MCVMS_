from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
import sqlite3
import ulid
import cv2
import json

from app.core.db import get_db
from app.api.dependencies import require_admin
from app.models.user import UserOut
from app.core.security import encrypt_url, decrypt_url
from app.core.clock import Clock
from app.sources.rtsp import RTSPSource

router = APIRouter(prefix="/cameras", tags=["cameras"])

class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    features: dict = {"vehicles": True, "id_check": False}

class CameraOut(BaseModel):
    id: str
    name: str
    enabled: bool
    features: dict
    width: int | None
    height: int | None
    fps: float | None
    status: str

@router.get("", response_model=List[CameraOut])
def list_cameras(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
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

@router.post("", response_model=CameraOut)
def create_camera(
    cam: CameraCreate,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    cam_id = str(ulid.ULID())
    enc_url = encrypt_url(cam.rtsp_url)
    features_json = json.dumps(cam.features)
    
    db.execute(
        "INSERT INTO cameras (id, name, rtsp_url_enc, enabled, features_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cam_id, cam.name, enc_url, 1, features_json, "unknown", Clock().now_ms())
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
    import os
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000"
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        return {"status": "failed", "reason": "Could not open stream"}
        
    ret, frame = cap.read()
    if not ret:
        cap.release()
        return {"status": "failed", "reason": "Could not read frame"}
        
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    
    db.execute("UPDATE cameras SET width=?, height=?, fps=?, status=? WHERE id=?", (width, height, fps, "online", cam_id))
    
    return {"status": "ok", "width": width, "height": height, "fps": fps}

@router.get("/{cam_id}/snapshot")
def get_snapshot(
    cam_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT rtsp_url_enc FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
        
    url = decrypt_url(row["rtsp_url_enc"])
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise HTTPException(status_code=503, detail="Could not open stream")
        
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        raise HTTPException(status_code=503, detail="Could not read frame")
        
    _, buffer = cv2.imencode('.jpg', frame)
    return Response(content=buffer.tobytes(), media_type="image/jpeg")
