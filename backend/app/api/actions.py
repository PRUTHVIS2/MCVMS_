"""Registered Actions management API.

docs/04_ZONES_AND_RULES.md, docs/08_API_AND_UI.md:
- CRUD for registered actions on special zones.
- 422 'zone_not_special' if zone kind is normal.
- Pydantic validation of action spec (template/shape applicability, catalogue, ops, schedule, dates).
- Dry-run evaluation on stored clips without creating alerts.
- Audit logging and runtime hot-reload.
"""

import datetime
import json
import logging
import sqlite3
from pathlib import Path
from typing import Annotated, Any

import cv2
import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.attributes.store import AttributeStore
from app.core.audit import log_audit
from app.core.clock import Clock
from app.core.db import get_db
from app.core.geometry import denormalize_points
from app.models.user import UserOut
from app.pipeline.camera_runtime import reload_camera_rules
from app.rules.engine import CompiledRule, CompiledZone, RuleEngine, RulesConfig
from app.rules.models import (
    RegisteredActionSpec,
    ZoneSpec,
    validate_rule_zone_compatibility,
)
from app.vision.detector import Detector
from app.vision.tracker import Tracker

logger = logging.getLogger(__name__)
router = APIRouter(tags=["actions"])


class ActionOut(BaseModel):
    id: str
    zone_id: str
    name: str
    spec: dict[str, Any]
    severity: str
    enabled: bool
    valid_from: int | None = None
    valid_until: int | None = None
    created_by: str | None = None
    created_at: int
    updated_at: int


class ActionUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    spec: RegisteredActionSpec | None = None


class DryRunRequest(BaseModel):
    clip_id: str | None = None
    clip_path: str | None = None
    max_frames: int | None = 300


class DraftDryRunRequest(BaseModel):
    zone_id: str
    spec: RegisteredActionSpec
    clip_id: str | None = None
    clip_path: str | None = None
    max_frames: int | None = 300


class SampleClipInfo(BaseModel):
    id: str
    name: str
    path: str
    category: str


class DryRunDecision(BaseModel):
    kind: str
    track_id: int
    ts_ms: int
    confidence: float
    evidence: dict[str, Any] = {}
    dry_run: bool = True


class DryRunResponse(BaseModel):
    action_id: str
    rule_name: str
    total_frames_processed: int
    decisions_count: int
    decisions: list[DryRunDecision]


def _row_to_zone_spec(row: sqlite3.Row) -> ZoneSpec:
    pts_raw = json.loads(row["points_json"])
    return ZoneSpec(
        id=row["id"],
        camera_id=row["camera_id"],
        name=row["name"],
        kind=row["kind"],
        shape=row["shape"],
        points=pts_raw,
        direction=row["direction"],
        is_read_area=bool(row["is_read_area"]),
        enabled=bool(row["enabled"])
    )


@router.get("/zones/{zone_id}/actions", response_model=list[ActionOut])
def list_actions_for_zone(
    zone_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    zone = db.execute("SELECT id FROM zones WHERE id = ?", (zone_id,)).fetchone()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    rows = db.execute(
        "SELECT * FROM registered_actions WHERE zone_id = ? ORDER BY created_at ASC",
        (zone_id,)
    ).fetchall()

    return [
        ActionOut(
            id=r["id"],
            zone_id=r["zone_id"],
            name=r["name"],
            spec=json.loads(r["spec_json"]),
            severity=r["severity"],
            enabled=bool(r["enabled"]),
            valid_from=r["valid_from"],
            valid_until=r["valid_until"],
            created_by=r["created_by"],
            created_at=r["created_at"],
            updated_at=r["updated_at"]
        ) for r in rows
    ]


@router.post("/zones/{zone_id}/actions", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
def create_action(
    zone_id: str,
    action_in: RegisteredActionSpec,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    zone = db.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    # Invariant: Normal zone cannot take registered actions
    if zone["kind"] == "normal":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "zone_not_special", "message": "Registered actions require a special zone"}
        )

    # Check template and shape compatibility
    zone_spec = _row_to_zone_spec(zone)
    try:
        validate_rule_zone_compatibility(action_in, zone_spec)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

    action_id = str(ulid.ULID())
    now = Clock().now_ms()
    severity = action_in.response.severity
    spec_json = action_in.model_dump_json(by_alias=True)

    valid_from_ms = None
    if action_in.valid and action_in.valid.from_date:
        dt = datetime.datetime.fromisoformat(action_in.valid.from_date).replace(tzinfo=datetime.UTC)
        valid_from_ms = int(dt.timestamp() * 1000)

    valid_until_ms = None
    if action_in.valid and action_in.valid.until_date:
        dt = datetime.datetime.fromisoformat(action_in.valid.until_date).replace(tzinfo=datetime.UTC)
        valid_until_ms = int(dt.timestamp() * 1000)

    try:
        db.execute(
            """
            INSERT INTO registered_actions
            (id, zone_id, name, spec_json, severity, enabled, valid_from, valid_until, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                zone_id,
                action_in.name,
                spec_json,
                severity,
                1,
                valid_from_ms,
                valid_until_ms,
                current_user.id,
                now,
                now
            )
        )
    except sqlite3.IntegrityError as e:
        # DB trigger ra_special_only_ins safety net
        if "registered actions require a special zone" in str(e):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "zone_not_special", "message": "Registered actions require a special zone"}
            ) from e
        raise

    log_audit(
        user_id=current_user.id,
        action="action_created",
        target=action_id,
        detail={"zone_id": zone_id, "name": action_in.name, "severity": severity}
    )

    reload_camera_rules(zone["camera_id"], db)

    return ActionOut(
        id=action_id,
        zone_id=zone_id,
        name=action_in.name,
        spec=json.loads(spec_json),
        severity=severity,
        enabled=True,
        valid_from=valid_from_ms,
        valid_until=valid_until_ms,
        created_by=current_user.id,
        created_at=now,
        updated_at=now
    )


@router.get("/actions/sample-clips", response_model=list[SampleClipInfo])
def list_sample_clips(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    """List available sample and stored video clips for dry-run simulation."""
    workspace_root = Path(__file__).resolve().parent.parent.parent.parent
    clips_list: list[SampleClipInfo] = []

    # 1. Synthetic clips
    synth_dir = workspace_root / "backend" / "tests" / "synthetic"
    if synth_dir.exists():
        for p in sorted(synth_dir.glob("*.mp4")):
            clips_list.append(
                SampleClipInfo(
                    id=f"synth_{p.stem}",
                    name=f"Synthetic: {p.stem.replace('_', ' ').title()}",
                    path=str(p.relative_to(workspace_root)).replace("\\", "/"),
                    category="synthetic"
                )
            )

    # 2. Test data events clips
    test_events_dir = workspace_root / "test_data" / "events"
    if test_events_dir.exists():
        for p in sorted(test_events_dir.glob("*.mp4")):
            clips_list.append(
                SampleClipInfo(
                    id=f"event_{p.stem}",
                    name=f"Recorded: {p.stem.replace('_', ' ').title()}",
                    path=str(p.relative_to(workspace_root)).replace("\\", "/"),
                    category="recorded"
                )
            )

    # 3. Database clips
    try:
        rows = db.execute("SELECT id, path FROM clips ORDER BY started_at DESC LIMIT 20").fetchall()
        for r in rows:
            if r["path"]:
                cp = Path(r["path"])
                rel_path = str(cp.relative_to(workspace_root)).replace("\\", "/") if cp.is_relative_to(workspace_root) else str(cp)
                clips_list.append(
                    SampleClipInfo(
                        id=r["id"],
                        name=f"Clip: {r['id'][:12]}",
                        path=rel_path,
                        category="stored"
                    )
                )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Failed to list database clips: {e}")

    return clips_list


@router.post("/actions/dry-run-draft", response_model=DryRunResponse)
def dry_run_draft_action(
    req: DraftDryRunRequest,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    """Evaluate a draft registered action spec on a zone without saving it."""
    zone_row = db.execute("SELECT * FROM zones WHERE id = ?", (req.zone_id,)).fetchone()
    if not zone_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    if zone_row["kind"] == "normal":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "zone_not_special", "message": "Dry-run actions require a special zone"}
        )

    zone_spec = _row_to_zone_spec(zone_row)
    try:
        validate_rule_zone_compatibility(req.spec, zone_spec)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

    return _execute_dry_run(
        zone_row=zone_row,
        spec=req.spec,
        action_id="draft_action",
        clip_id=req.clip_id,
        clip_path=req.clip_path,
        max_frames=req.max_frames,
        db=db
    )


@router.get("/actions/{action_id}", response_model=ActionOut)
def get_action(
    action_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT * FROM registered_actions WHERE id = ?", (action_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    return ActionOut(
        id=row["id"],
        zone_id=row["zone_id"],
        name=row["name"],
        spec=json.loads(row["spec_json"]),
        severity=row["severity"],
        enabled=bool(row["enabled"]),
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )


@router.patch("/actions/{action_id}", response_model=ActionOut)
def update_action(
    action_id: str,
    update_in: ActionUpdate,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT * FROM registered_actions WHERE id = ?", (action_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    zone = db.execute("SELECT * FROM zones WHERE id = ?", (row["zone_id"],)).fetchone()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated zone not found")

    now = Clock().now_ms()
    new_name = update_in.name if update_in.name is not None else row["name"]
    new_enabled = update_in.enabled if update_in.enabled is not None else bool(row["enabled"])

    if update_in.spec is not None:
        zone_spec = _row_to_zone_spec(zone)
        try:
            validate_rule_zone_compatibility(update_in.spec, zone_spec)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

        new_severity = update_in.spec.response.severity
        new_spec_json = update_in.spec.model_dump_json(by_alias=True)

        valid_from_ms = None
        if update_in.spec.valid and update_in.spec.valid.from_date:
            dt = datetime.datetime.fromisoformat(update_in.spec.valid.from_date).replace(tzinfo=datetime.UTC)
            valid_from_ms = int(dt.timestamp() * 1000)

        valid_until_ms = None
        if update_in.spec.valid and update_in.spec.valid.until_date:
            dt = datetime.datetime.fromisoformat(update_in.spec.valid.until_date).replace(tzinfo=datetime.UTC)
            valid_until_ms = int(dt.timestamp() * 1000)
    else:
        new_severity = row["severity"]
        new_spec_json = row["spec_json"]
        valid_from_ms = row["valid_from"]
        valid_until_ms = row["valid_until"]

    db.execute(
        """
        UPDATE registered_actions
        SET name = ?, spec_json = ?, severity = ?, enabled = ?, valid_from = ?, valid_until = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            new_name,
            new_spec_json,
            new_severity,
            1 if new_enabled else 0,
            valid_from_ms,
            valid_until_ms,
            now,
            action_id
        )
    )

    log_audit(
        user_id=current_user.id,
        action="action_updated",
        target=action_id,
        detail={"name": new_name, "severity": new_severity, "enabled": new_enabled}
    )

    reload_camera_rules(zone["camera_id"], db)

    return ActionOut(
        id=action_id,
        zone_id=row["zone_id"],
        name=new_name,
        spec=json.loads(new_spec_json),
        severity=new_severity,
        enabled=new_enabled,
        valid_from=valid_from_ms,
        valid_until=valid_until_ms,
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=now
    )


@router.delete("/actions/{action_id}")
def delete_action(
    action_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    row = db.execute("SELECT * FROM registered_actions WHERE id = ?", (action_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    zone = db.execute("SELECT camera_id FROM zones WHERE id = ?", (row["zone_id"],)).fetchone()
    camera_id = zone["camera_id"] if zone else None

    db.execute("DELETE FROM registered_actions WHERE id = ?", (action_id,))

    log_audit(
        user_id=current_user.id,
        action="action_deleted",
        target=action_id,
        detail={"name": row["name"], "zone_id": row["zone_id"]}
    )

    if camera_id:
        reload_camera_rules(camera_id, db)

    return {"status": "deleted", "id": action_id}


def _execute_dry_run(
    zone_row: sqlite3.Row,
    spec: RegisteredActionSpec,
    action_id: str,
    clip_id: str | None,
    clip_path: str | None,
    max_frames: int | None,
    db: sqlite3.Connection
) -> DryRunResponse:
    clip_file: Path | None = None
    if clip_id:
        c = db.execute("SELECT path FROM clips WHERE id = ?", (clip_id,)).fetchone()
        if c and c["path"]:
            clip_file = Path(c["path"])
    elif clip_path:
        clip_file = Path(clip_path)
        if not clip_file.exists():
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent
            cand = workspace_root / clip_path
            if cand.exists():
                clip_file = cand

    if not clip_file or not clip_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Clip file not found: {clip_file or clip_path}"
        )

    pts_raw = json.loads(zone_row["points_json"])
    cap = cv2.VideoCapture(str(clip_file))
    if not cap.isOpened():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not open video file")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    pts = [(float(p[0]), float(p[1])) for p in pts_raw]
    if all(0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0 for p in pts):
        pts = denormalize_points(pts, w, h)

    cz = CompiledZone(
        id=zone_row["id"],
        name=zone_row["name"],
        kind=zone_row["kind"],
        shape=zone_row["shape"],
        points=pts,
        direction=zone_row["direction"],
        is_read_area=bool(zone_row["is_read_area"])
    )
    cr = CompiledRule(
        id=action_id,
        zone_id=zone_row["id"],
        spec=spec
    )

    rule_engine = RuleEngine(rules=[cr], zones={cz.id: cz}, cfg=RulesConfig())
    detector = Detector()
    tracker = Tracker()
    attr_store = AttributeStore()

    frame_idx = 0
    max_f = max_frames or 300
    all_decisions: list[DryRunDecision] = []

    frame_interval_ms = int(1000.0 / fps) if fps > 0 else 40
    start_ts_ms = Clock().now_ms()

    while frame_idx < max_f:
        ret, frame_bgr = cap.read()
        if not ret or frame_bgr is None:
            break

        now_ms = start_ts_ms + (frame_idx * frame_interval_ms)
        detections = detector.detect(frame_bgr)
        tracks = tracker.update(detections, frame_bgr, ts_ms=now_ms)

        from app.core.types import TrackedFrame
        tf = TrackedFrame(
            camera_id=zone_row["camera_id"],
            ts_ms=now_ms,
            frame_size=(w, h),
            objects=tracks
        )

        decisions = rule_engine.step(
            frame=tf,
            attrs=attr_store.all_attrs(),
            now_ms=now_ms,
            exempt=lambda _aid, _ts: False
        )

        for d in decisions:
            all_decisions.append(
                DryRunDecision(
                    kind=d.kind,
                    track_id=d.track_id,
                    ts_ms=d.ts_ms,
                    confidence=d.confidence,
                    evidence=d.evidence or {},
                    dry_run=True
                )
            )

        frame_idx += 1

    cap.release()

    return DryRunResponse(
        action_id=action_id,
        rule_name=spec.name,
        total_frames_processed=frame_idx,
        decisions_count=len(all_decisions),
        decisions=all_decisions
    )


@router.post("/actions/{action_id}/dry-run", response_model=DryRunResponse)
def dry_run_action(
    action_id: str,
    req: DryRunRequest,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    """Evaluate an action against a video clip without writing alerts or real events."""
    row = db.execute("SELECT * FROM registered_actions WHERE id = ?", (action_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    zone_row = db.execute("SELECT * FROM zones WHERE id = ?", (row["zone_id"],)).fetchone()
    if not zone_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated zone not found")

    spec = RegisteredActionSpec.model_validate_json(row["spec_json"])
    return _execute_dry_run(
        zone_row=zone_row,
        spec=spec,
        action_id=action_id,
        clip_id=req.clip_id,
        clip_path=req.clip_path,
        max_frames=req.max_frames,
        db=db
    )
