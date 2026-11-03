"""Calendar exemptions API.

docs/04_ZONES_AND_RULES.md, docs/08_API_AND_UI.md:
- CRUD for calendar exemptions (holidays, exam days, special events).
- Date validation (YYYY-MM-DD, date_from <= date_to).
- Scopes: 'all', 'camera', 'action'.
- Audit logging.
"""

import datetime
import sqlite3
from typing import Annotated, Literal

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.dependencies import require_admin
from app.core.audit import log_audit
from app.core.clock import Clock
from app.core.db import get_db
from app.models.user import UserOut

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarExemptionCreate(BaseModel):
    label: str
    date_from: str = Field(..., description="Start date YYYY-MM-DD (inclusive)")
    date_to: str = Field(..., description="End date YYYY-MM-DD (inclusive)")
    scope: Literal["all", "camera", "action"] = "all"
    camera_id: str | None = None
    action_id: str | None = None

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Date '{v}' must be in YYYY-MM-DD format") from None
        return v

    @model_validator(mode="after")
    def validate_dates_and_scope(self) -> "CalendarExemptionCreate":
        d_from = datetime.date.fromisoformat(self.date_from)
        d_to = datetime.date.fromisoformat(self.date_to)
        if d_from > d_to:
            raise ValueError(f"date_from '{self.date_from}' cannot be after date_to '{self.date_to}'")

        if self.scope == "camera" and not self.camera_id:
            raise ValueError("scope 'camera' requires 'camera_id'")
        if self.scope == "action" and not self.action_id:
            raise ValueError("scope 'action' requires 'action_id'")
        return self


class CalendarExemptionOut(BaseModel):
    id: str
    label: str
    date_from: str
    date_to: str
    scope: str
    camera_id: str | None = None
    action_id: str | None = None
    created_by: str | None = None
    created_at: int


@router.get("", response_model=list[CalendarExemptionOut])
def list_calendar_exemptions(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)],
    camera_id: str | None = None,
    action_id: str | None = None
):
    query = "SELECT * FROM calendar_exemptions WHERE 1=1"
    params: list = []

    if camera_id:
        query += " AND (scope = 'all' OR (scope = 'camera' AND camera_id = ?))"
        params.append(camera_id)
    if action_id:
        query += " AND (scope = 'all' OR (scope = 'action' AND action_id = ?))"
        params.append(action_id)

    query += " ORDER BY date_from ASC"
    rows = db.execute(query, params).fetchall()

    return [
        CalendarExemptionOut(
            id=r["id"],
            label=r["label"],
            date_from=r["date_from"],
            date_to=r["date_to"],
            scope=r["scope"],
            camera_id=r["camera_id"],
            action_id=r["action_id"],
            created_by=r["created_by"],
            created_at=r["created_at"]
        ) for r in rows
    ]


@router.post("", response_model=CalendarExemptionOut, status_code=status.HTTP_201_CREATED)
def create_calendar_exemption(
    ex_in: CalendarExemptionCreate,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    # Verify foreign keys if provided
    if ex_in.camera_id:
        cam = db.execute("SELECT id FROM cameras WHERE id = ?", (ex_in.camera_id,)).fetchone()
        if not cam:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Camera {ex_in.camera_id} not found")

    if ex_in.action_id:
        act = db.execute("SELECT id FROM registered_actions WHERE id = ?", (ex_in.action_id,)).fetchone()
        if not act:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Action {ex_in.action_id} not found")

    exemption_id = str(ulid.ULID())
    now = Clock().now_ms()

    db.execute(
        """
        INSERT INTO calendar_exemptions (id, label, date_from, date_to, scope, action_id, camera_id, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exemption_id,
            ex_in.label,
            ex_in.date_from,
            ex_in.date_to,
            ex_in.scope,
            ex_in.action_id,
            ex_in.camera_id,
            current_user.id,
            now
        )
    )

    log_audit(
        user_id=current_user.id,
        action="calendar_exemption_created",
        target=exemption_id,
        detail={
            "label": ex_in.label,
            "date_from": ex_in.date_from,
            "date_to": ex_in.date_to,
            "scope": ex_in.scope
        }
    )

    return CalendarExemptionOut(
        id=exemption_id,
        label=ex_in.label,
        date_from=ex_in.date_from,
        date_to=ex_in.date_to,
        scope=ex_in.scope,
        camera_id=ex_in.camera_id,
        action_id=ex_in.action_id,
        created_by=current_user.id,
        created_at=now
    )


@router.delete("/{exemption_id}")
def delete_calendar_exemption(
    exemption_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT * FROM calendar_exemptions WHERE id = ?", (exemption_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar exemption not found")

    db.execute("DELETE FROM calendar_exemptions WHERE id = ?", (exemption_id,))

    log_audit(
        user_id=current_user.id,
        action="calendar_exemption_deleted",
        target=exemption_id,
        detail={"label": row["label"]}
    )

    return {"status": "deleted", "id": exemption_id}

