"""Events API endpoints.

docs/08_API_AND_UI.md section 1, 2:
- GET /events (filters: camera, zone, action, severity, status, date range, vehicle)
- GET /events/{id}
- POST /events/{id}/ack (owner, admin, incharge)
- POST /events/{id}/false-alarm (owner, admin only; incharge forbidden; requires reason)
"""

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
