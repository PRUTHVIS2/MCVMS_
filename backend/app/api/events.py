"""Events API endpoints.

docs/08_API_AND_UI.md section 1, 2:
- GET /events (filters: camera, zone, action, severity, status, date range, vehicle)
- GET /events/{id}
- POST /events/{id}/ack (owner, admin, incharge)
- POST /events/{id}/false-alarm (owner, admin only; incharge forbidden; requires reason)
"""

from pathlib import Path
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, require_admin, require_incharge
from app.core.clock import Clock
from app.core.db import get_db
from app.models.user import UserOut
from app.services.events import EventService

router = APIRouter(prefix="/events", tags=["events"])
event_service = EventService()
clock = Clock()


class FalseAlarmRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Mandatory reason for marking false alarm")


@router.get("", response_model=list[dict[str, Any]])
def list_events(
    current_user: Annotated[UserOut, Depends(get_current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    camera_id: str | None = Query(None),
    zone_id: str | None = Query(None),
    action_id: str | None = Query(None),
    severity: str | None = Query(None),
    status: str | None = Query(None),
    from_ts: int | None = Query(None),
    to_ts: int | None = Query(None),
    vehicle_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200)
):
    """List recorded events with optional filters."""
    # Scope in-charge users to their assigned cameras if specified
    effective_camera_id = camera_id
    if current_user.role == "incharge" and current_user.cameras:
        if camera_id and camera_id not in current_user.cameras:
            return []
        elif not camera_id and len(current_user.cameras) == 1:
            effective_camera_id = current_user.cameras[0]

    return event_service.get_events(
        db_conn=db,
        camera_id=effective_camera_id,
        zone_id=zone_id,
        action_id=action_id,
        severity=severity,
        status=status,
        from_ts=from_ts,
        to_ts=to_ts,
        vehicle_id=vehicle_id,
        limit=limit
    )


@router.get("/{event_id}", response_model=dict[str, Any])
def get_event(
    event_id: str,
    current_user: Annotated[UserOut, Depends(get_current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    """Retrieve event details by ID."""
    event = event_service.get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if current_user.role == "incharge" and current_user.cameras and event["camera_id"] not in current_user.cameras:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Camera access forbidden")

    return event


@router.post("/{event_id}/ack", response_model=dict[str, Any])
def acknowledge_event(
    event_id: str,
    current_user: Annotated[UserOut, Depends(require_incharge)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    """Acknowledge an open event. Permitted for owner, admin, incharge."""
    try:
        now_ms = clock.now_ms()
        return event_service.acknowledge_event(event_id, current_user.id, now_ms, db)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{event_id}/false-alarm", response_model=dict[str, Any])
def mark_false_alarm(
    event_id: str,
    body: FalseAlarmRequest,
    current_user: Annotated[UserOut, Depends(require_admin)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    """Mark an event as a false alarm. Permitted for owner, admin only (incharge forbidden)."""
    try:
        now_ms = clock.now_ms()
        return event_service.mark_false_alarm(
            event_id=event_id,
            user_id=current_user.id,
            reason=body.reason,
            now_ms=now_ms,
            role=current_user.role,
            db_conn=db
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _stream_video_range(file_path: Path, range_header: str | None) -> StreamingResponse | FileResponse:
    file_size = file_path.stat().st_size
    if not range_header or not range_header.startswith("bytes="):
        return FileResponse(
            file_path,
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)}
        )

    try:
        range_spec = range_header.replace("bytes=", "").split("-")
        start = int(range_spec[0]) if range_spec[0] else 0
        end = int(range_spec[1]) if len(range_spec) > 1 and range_spec[1] else file_size - 1
        if end >= file_size:
            end = file_size - 1
        if start > end or start >= file_size:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid Range")

        chunk_size = end - start + 1

        def iter_file():
            with open(file_path, "rb") as f:
                f.seek(start)
                bytes_left = chunk_size
                while bytes_left > 0:
                    read_len = min(65536, bytes_left)
                    data = f.read(read_len)
                    if not data:
                        break
                    bytes_left -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": "video/mp4"
            }
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail=str(e))


@router.get("/{event_id}/clip")
def get_event_clip(
    event_id: str,
    request: Request,
    current_user: Annotated[UserOut, Depends(get_current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    """Stream event clip MP4 with HTTP 206 range request support."""
    event = event_service.get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if current_user.role == "incharge" and current_user.cameras and event["camera_id"] not in current_user.cameras:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Camera access forbidden")

    clip_id = event.get("clip_id")
    if not clip_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event has no clip")

    clip_row = db.execute("SELECT path FROM clips WHERE id = ?", (clip_id,)).fetchone()
    clip_path = Path(clip_row["path"]) if clip_row and clip_row["path"] else None

    if not clip_path or not clip_path.exists():
        # Fallback search in data/clips
        matches = list(Path("data/clips").glob(f"**/{clip_id}.mp4"))
        if matches:
            clip_path = matches[0]

    if not clip_path or not clip_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Clip file not found: {clip_id}")

    range_header = request.headers.get("range")
    return _stream_video_range(clip_path, range_header)


@router.get("/{event_id}/keyframes/{label}")
def get_event_keyframe(
    event_id: str,
    label: str,
    current_user: Annotated[UserOut, Depends(get_current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    """Retrieve keyframe image (first, anchor, last) for an event clip."""
    event = event_service.get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if current_user.role == "incharge" and current_user.cameras and event["camera_id"] not in current_user.cameras:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Camera access forbidden")

    clip_id = event.get("clip_id")
    if not clip_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event has no clip")

    clip_row = db.execute("SELECT path FROM clips WHERE id = ?", (clip_id,)).fetchone()
    clip_path = Path(clip_row["path"]) if clip_row and clip_row["path"] else None
    if not clip_path or not clip_path.exists():
        matches = list(Path("data/clips").glob(f"**/{clip_id}.mp4"))
        if matches:
            clip_path = matches[0]

    if not clip_path or not clip_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    parent = clip_path.parent
    # Check directly by label or full filename
    target_img = parent / f"{clip_id}_key_{label}.jpg"
    if not target_img.exists():
        target_img = parent / label
    if not target_img.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyframe image not found")

    return FileResponse(target_img, media_type="image/jpeg")
