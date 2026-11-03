"""Supervised per-camera runtime pipeline.

docs/04_ZONES_AND_RULES.md, docs/02_ARCHITECTURE.md:
Wires together FrameSource, Analyzer, RuleEngine, AttributeStore, and EventService.
Supports hot-reload of compiled rules and zones without pipeline interruption.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path

from app.attributes.store import AttributeStore
from app.core.clock import Clock
from app.core.db import get_connection
from app.core.types import TrackedFrame
from app.pipeline.analyzer import Analyzer
from app.recorder.clipper import Clipper
from app.rules.engine import CompiledRule, CompiledZone, RuleEngine, RulesConfig
from app.rules.models import RegisteredActionSpec
from app.services.events import EventService
from app.services.exemptions import is_calendar_exempt

logger = logging.getLogger(__name__)

active_runtimes: dict[str, "CameraRuntime"] = {}


def register_runtime(runtime: "CameraRuntime") -> None:
    """Register an active camera runtime for hot-reloading."""
    active_runtimes[runtime.camera_id] = runtime


def unregister_runtime(camera_id: str) -> None:
    """Unregister a stopped camera runtime."""
    active_runtimes.pop(camera_id, None)


def get_runtime(camera_id: str) -> "CameraRuntime | None":
    """Get active camera runtime if registered."""
    return active_runtimes.get(camera_id)


def reload_camera_rules(camera_id: str, db_conn: sqlite3.Connection | None = None) -> bool:
    """Hot-reload rules for an active camera runtime if running."""
    rt = active_runtimes.get(camera_id)
    if rt is not None:
        rt.reload_from_db(db_conn)
        return True
    return False


def load_rules_for_camera(
    camera_id: str,
    db_conn: sqlite3.Connection
) -> tuple[list[CompiledRule], dict[str, CompiledZone]]:
    """Load active compiled rules and zones for a given camera from SQLite."""
    # 1. Load zones
    zones_rows = db_conn.execute(
        "SELECT id, name, kind, shape, points_json, direction, is_read_area FROM zones WHERE camera_id = ?",
        (camera_id,)
    ).fetchall()

    compiled_zones: dict[str, CompiledZone] = {}
    for r in zones_rows:
        try:
            points_raw = json.loads(r["points_json"])
            pts = [(float(p[0]), float(p[1])) for p in points_raw]
        except (json.JSONDecodeError, TypeError, ValueError):
            pts = []
        cz = CompiledZone(
            id=r["id"],
            name=r["name"],
            kind=r["kind"],
            shape=r["shape"],
            points=pts,
            direction=r["direction"],
            is_read_area=bool(r["is_read_area"])
        )
        compiled_zones[cz.id] = cz

    # 2. Load armed registered actions on special zones
    actions_rows = db_conn.execute(
        """
        SELECT a.id, a.zone_id, a.name, a.spec_json
        FROM registered_actions a
        JOIN zones z ON a.zone_id = z.id
        WHERE z.camera_id = ? AND a.enabled = 1 AND z.kind = 'special'
        """,
        (camera_id,)
    ).fetchall()

    compiled_rules: list[CompiledRule] = []
    for r in actions_rows:
        try:
            spec = RegisteredActionSpec.model_validate_json(r["spec_json"])
            cr = CompiledRule(
                id=r["id"],
                zone_id=r["zone_id"],
                spec=spec
            )
            compiled_rules.append(cr)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error compiling registered action {r['id']}: {e}")

    return compiled_rules, compiled_zones


class CameraRuntime:
    """Supervised execution pipeline for a single camera."""

    def __init__(
        self,
        camera_id: str,
        analyzer: Analyzer,
        event_service: EventService,
        rules: list[CompiledRule] | None = None,
        zones: dict[str, CompiledZone] | None = None,
        attr_store: AttributeStore | None = None,
        clipper: Clipper | None = None,
        clock: Clock | None = None,
        camera_name: str | None = None,
        source_file: Path | None = None,
        rules_config: RulesConfig | None = None
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name or camera_id
        self.analyzer = analyzer
        self.event_service = event_service
        self.attr_store = attr_store or AttributeStore()
        self.clipper = clipper
        self.clock = clock or Clock()
        self.source_file = source_file
        self.rules_config = rules_config or RulesConfig()

        self._lock = threading.Lock()
        self.rules = rules or []
        self.zones = zones or {}
        self.engine = RuleEngine(rules=self.rules, zones=self.zones, cfg=self.rules_config)

        self.last_frame_ts: int = 0
        self.processed_frames: int = 0
        self.is_running: bool = False

        # Subscribe to analyzer
        self.analyzer.subscribe(self.on_tracked_frame)

    def reload_rules(self, rules: list[CompiledRule], zones: dict[str, CompiledZone]) -> None:
        """Thread-safe hot reload of rules and zones."""
        with self._lock:
            self.rules = rules
            self.zones = zones
            self.engine = RuleEngine(rules=rules, zones=zones, cfg=self.rules_config)
            logger.info(
                f"CameraRuntime({self.camera_id}) hot-reloaded: {len(rules)} rules, {len(zones)} zones"
            )

    def reload_from_db(self, db_conn: sqlite3.Connection | None = None) -> None:
        """Reload active rules and zones from the database."""
        conn = db_conn or get_connection()
        rules, zones = load_rules_for_camera(self.camera_id, conn)
        self.reload_rules(rules, zones)

    def on_tracked_frame(self, frame: TrackedFrame) -> None:
        """Callback invoked on every TrackedFrame emitted by Analyzer."""
        self.last_frame_ts = frame.ts_ms
        self.processed_frames += 1
        now_ms = frame.ts_ms

        conn = get_connection()

        def exempt_callback(action_id: str, ts: int) -> bool:
            return is_calendar_exempt(self.camera_id, action_id, ts, conn)

        with self._lock:
            attrs = self.attr_store.all_attrs()
            decisions = self.engine.step(
                frame=frame,
                attrs=attrs,
                now_ms=now_ms,
                exempt=exempt_callback
            )
            # Find rule specs for decisions
            rules_by_id = {r.id: r.spec for r in self.rules}

        for dec in decisions:
            spec = rules_by_id.get(dec.rule_id)
            try:
                self.event_service.handle_decision(
                    decision=dec,
                    camera_id=self.camera_id,
                    db_conn=conn,
                    camera_name=self.camera_name,
                    rule_spec=spec,
                    source_file=self.source_file,
                    now_ms=now_ms
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error handling decision for camera {self.camera_id}: {e}")

    def start(self) -> None:
        """Start the camera runtime pipeline."""
        self.is_running = True
        self.analyzer.start()
        logger.info(f"CameraRuntime({self.camera_id}) started.")

    def stop(self) -> None:
        """Gracefully stop runtime and flush open events."""
        self.is_running = False
        self.analyzer.stop()

        # Flush open events from engine
        now_ms = self.last_frame_ts or self.clock.now_ms()
        conn = get_connection()

        with self._lock:
            flush_decisions = self.engine.flush(now_ms)
            rules_by_id = {r.id: r.spec for r in self.rules}

        for dec in flush_decisions:
            spec = rules_by_id.get(dec.rule_id)
            try:
                self.event_service.handle_decision(
                    decision=dec,
                    camera_id=self.camera_id,
                    db_conn=conn,
                    camera_name=self.camera_name,
                    rule_spec=spec,
                    source_file=self.source_file,
                    now_ms=now_ms
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error flushing decision for camera {self.camera_id}: {e}")

        logger.info(f"CameraRuntime({self.camera_id}) stopped.")
