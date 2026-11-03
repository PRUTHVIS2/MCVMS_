"""Alerts API endpoints.

docs/08_API_AND_UI.md section 1, 2:
- GET /alerts
- POST /alerts/{id}/ack (owner, admin, incharge)
- POST /alerts/{id}/dismiss (owner, admin only; incharge forbidden; requires reason)
"""

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, require_admin, require_incharge
from app.core.clock import Clock
from app.core.db import get_db
from app.models.user import UserOut
from app.services.alerts import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])
alert_service = AlertService()
clock = Clock()


class DismissAlertRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Mandatory reason for dismissing alert")


@router.get("", response_model=list[dict[str, Any]])
def list_alerts(
    current_user: Annotated[UserOut, Depends(get_current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
    level: str | None = Query(None),
    kind: str | None = Query(None),
    camera_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200)
):
    """List system and rule alerts."""
    # Also perform auto-expiry of overdue alerts
    now_ms = clock.now_ms()
    alert_service.expire_alerts(now_ms, db)

    return alert_service.get_alerts(
        db_conn=db,
        status=status_filter,
        level=level,
        kind=kind,
        camera_id=camera_id,
        limit=limit
    )


@router.post("/{alert_id}/ack", response_model=dict[str, Any])
def acknowledge_alert(
    alert_id: str,
    current_user: Annotated[UserOut, Depends(require_incharge)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    """Acknowledge an open alert. Permitted for owner, admin, incharge."""
    try:
        now_ms = clock.now_ms()
        return alert_service.acknowledge_alert(alert_id, current_user.id, now_ms, db)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{alert_id}/dismiss", response_model=dict[str, Any])
def dismiss_alert(
    alert_id: str,
    body: DismissAlertRequest,
    current_user: Annotated[UserOut, Depends(require_admin)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    """Dismiss an alert. Permitted for owner, admin only (incharge forbidden; reason mandatory)."""
    try:
        now_ms = clock.now_ms()
        return alert_service.dismiss_alert(
            alert_id=alert_id,
            user_id=current_user.id,
            reason=body.reason,
            now_ms=now_ms,
            role=current_user.role,
            db_conn=db
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
