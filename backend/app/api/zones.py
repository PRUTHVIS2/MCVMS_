"""Zones management API.

docs/04_ZONES_AND_RULES.md, docs/08_API_AND_UI.md:
- CRUD for camera zones with geometry validation (polygon 3..20 points, line 2 points).
- Kind enforcement: normal vs special.
- 409 Conflict when downgrading a special zone with actions to normal.
- Audit logging and runtime hot-reload.
"""

import json
import sqlite3
from typing import Annotated, Literal

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError

from app.api.dependencies import require_admin, require_incharge
from app.core.audit import log_audit
from app.core.clock import Clock
from app.core.db import get_db
from app.models.user import UserOut
from app.pipeline.camera_runtime import reload_camera_rules
from app.rules.models import ZoneSpec

router = APIRouter(tags=["zones"])


class ZoneCreate(BaseModel):
    name: str
    kind: Literal["normal", "special"]
    shape: Literal["polygon", "line"]
    points: list[list[float]]
    direction: Literal["in", "out", "both"] | None = None
    is_read_area: bool = False
    enabled: bool = True


class ZoneUpdate(BaseModel):
    name: str | None = None
    kind: Literal["normal", "special"] | None = None
    shape: Literal["polygon", "line"] | None = None
    points: list[list[float]] | None = None
    direction: Literal["in", "out", "both"] | None = None
    is_read_area: bool | None = None
    enabled: bool | None = None


class ZoneOut(BaseModel):
    id: str
    camera_id: str
    name: str
    kind: str
    shape: str
    points: list[list[float]]
    direction: str | None = None
    is_read_area: bool
    enabled: bool
    created_at: int
    updated_at: int
    warning: str | None = None


@router.get("/cameras/{camera_id}/zones", response_model=list[ZoneOut])
def list_zones_for_camera(
    camera_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_incharge)]
):
    if current_user.role == "incharge" and camera_id not in current_user.cameras:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Camera access forbidden")
    cam = db.execute("SELECT id FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    if not cam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    rows = db.execute(
        "SELECT * FROM zones WHERE camera_id = ? ORDER BY created_at ASC",
        (camera_id,)
    ).fetchall()

    return [
        ZoneOut(
            id=r["id"],
            camera_id=r["camera_id"],
            name=r["name"],
            kind=r["kind"],
            shape=r["shape"],
            points=json.loads(r["points_json"]),
            direction=r["direction"],
            is_read_area=bool(r["is_read_area"]),
            enabled=bool(r["enabled"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"]
        ) for r in rows
    ]


@router.post("/cameras/{camera_id}/zones", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
def create_zone(
    camera_id: str,
    zone_in: ZoneCreate,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    cam = db.execute("SELECT id FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    if not cam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    # Geometry and model validation
    try:
        spec = ZoneSpec(
            camera_id=camera_id,
            name=zone_in.name,
            kind=zone_in.kind,
            shape=zone_in.shape,
            points=zone_in.points,
            direction=zone_in.direction,
            is_read_area=zone_in.is_read_area,
            enabled=zone_in.enabled
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

    zone_id = str(ulid.ULID())
    now = Clock().now_ms()

    db.execute(
        """
        INSERT INTO zones (id, camera_id, name, kind, shape, points_json, direction, is_read_area, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            zone_id,
            camera_id,
            spec.name,
            spec.kind,
            spec.shape,
            json.dumps(spec.points),
            spec.direction,
            1 if spec.is_read_area else 0,
            1 if spec.enabled else 0,
            now,
            now
        )
    )

    log_audit(
        user_id=current_user.id,
        action="zone_created",
        target=zone_id,
        detail={"camera_id": camera_id, "name": spec.name, "kind": spec.kind, "shape": spec.shape}
    )

    # Hot reload running pipelines
    reload_camera_rules(camera_id, db)

    return ZoneOut(
        id=zone_id,
        camera_id=camera_id,
        name=spec.name,
        kind=spec.kind,
        shape=spec.shape,
        points=spec.points,
        direction=spec.direction,
        is_read_area=spec.is_read_area,
        enabled=spec.enabled,
        created_at=now,
        updated_at=now
    )


@router.get("/zones/{zone_id}", response_model=ZoneOut)
def get_zone(
    zone_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    return ZoneOut(
        id=row["id"],
        camera_id=row["camera_id"],
        name=row["name"],
        kind=row["kind"],
        shape=row["shape"],
        points=json.loads(row["points_json"]),
        direction=row["direction"],
        is_read_area=bool(row["is_read_area"]),
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )


@router.patch("/zones/{zone_id}", response_model=ZoneOut)
def update_zone(
    zone_id: str,
    update_in: ZoneUpdate,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    # Check for downgrade conflict
    has_actions = db.execute("SELECT 1 FROM registered_actions WHERE zone_id = ?", (zone_id,)).fetchone() is not None
    if update_in.kind == "normal" and row["kind"] == "special" and has_actions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "zone_has_actions", "message": "Cannot downgrade zone kind to normal while registered actions exist"}
        )

    # Merge fields
    new_name = update_in.name if update_in.name is not None else row["name"]
    new_kind = update_in.kind if update_in.kind is not None else row["kind"]
    new_shape = update_in.shape if update_in.shape is not None else row["shape"]
    new_points = update_in.points if update_in.points is not None else json.loads(row["points_json"])
    new_direction = update_in.direction if update_in.direction is not None else row["direction"]
    new_is_read_area = update_in.is_read_area if update_in.is_read_area is not None else bool(row["is_read_area"])
    new_enabled = update_in.enabled if update_in.enabled is not None else bool(row["enabled"])

    # Validate merged spec
    try:
        spec = ZoneSpec(
            id=zone_id,
            camera_id=row["camera_id"],
            name=new_name,
            kind=new_kind,
            shape=new_shape,
            points=new_points,
            direction=new_direction,
            is_read_area=new_is_read_area,
            enabled=new_enabled
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

    warning = None
    if has_actions and (update_in.shape is not None or update_in.points is not None):
        warning = "Zone shape modified while registered actions exist. Re-running dry run is recommended."

    now = Clock().now_ms()
    db.execute(
        """
        UPDATE zones
        SET name = ?, kind = ?, shape = ?, points_json = ?, direction = ?, is_read_area = ?, enabled = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            spec.name,
            spec.kind,
            spec.shape,
            json.dumps(spec.points),
            spec.direction,
            1 if spec.is_read_area else 0,
            1 if spec.enabled else 0,
            now,
            zone_id
        )
    )

    log_audit(
        user_id=current_user.id,
        action="zone_updated",
        target=zone_id,
        detail={
            "camera_id": row["camera_id"],
            "changes": update_in.model_dump(exclude_unset=True)
        }
    )

    reload_camera_rules(row["camera_id"], db)

    return ZoneOut(
        id=zone_id,
        camera_id=row["camera_id"],
        name=spec.name,
        kind=spec.kind,
        shape=spec.shape,
        points=spec.points,
        direction=spec.direction,
        is_read_area=spec.is_read_area,
        enabled=spec.enabled,
        created_at=row["created_at"],
        updated_at=now,
        warning=warning
    )


@router.delete("/zones/{zone_id}")
def delete_zone(
    zone_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    camera_id = row["camera_id"]

    # Delete any registered actions attached to this zone
    action_rows = db.execute("SELECT id FROM registered_actions WHERE zone_id = ?", (zone_id,)).fetchall()
    deleted_action_ids = [r["id"] for r in action_rows]
    for aid in deleted_action_ids:
        db.execute("UPDATE events SET action_id = NULL WHERE action_id = ?", (aid,))
        db.execute("DELETE FROM calendar_exemptions WHERE action_id = ?", (aid,))
    if deleted_action_ids:
        db.execute("DELETE FROM registered_actions WHERE zone_id = ?", (zone_id,))

    db.execute("DELETE FROM zones WHERE id = ?", (zone_id,))

    log_audit(
        user_id=current_user.id,
        action="zone_deleted",
        target=zone_id,
        detail={"camera_id": camera_id, "deleted_action_ids": deleted_action_ids}
    )

    reload_camera_rules(camera_id, db)

    return {"status": "deleted", "id": zone_id, "actions_deleted": len(deleted_action_ids)}

