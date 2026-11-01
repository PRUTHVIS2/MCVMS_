"""Pure Rule Engine for zones and registered actions.

docs/04 s6:
Deterministic: identical input gives identical decisions.
State is per (rule, track).
The engine never reads a clock, never accesses DB, network, or disk, and never sleeps.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.geometry import check_line_crossing, denormalize_points, point_in_polygon
from app.core.types import TrackAttributes, TrackedFrame, TrackedObject
from app.rules.conditions import eval_where
from app.rules.escalation import pick_severity
from app.rules.models import RegisteredActionSpec, ZoneSpec, validate_rule_zone_compatibility
from app.rules.schedule import is_rule_armed


@dataclass
class Decision:
    """Decision emitted by the rule engine."""
    kind: str  # 'start' | 'update' | 'end'
    rule_id: str
    track_id: int | None
    ts_ms: int
    subject_snapshot: dict[str, Any]
    confidence: float
    evidence: dict[str, Any]


@dataclass
class CompiledZone:
    id: str
    name: str
    kind: str  # 'normal' | 'special'
    shape: str # 'polygon' | 'line'
    points: list[tuple[float, float]]  # Points (normalized 0..1 or pixel)
    direction: str | None = None    # 'in' | 'out' | 'both'
    is_read_area: bool = False


@dataclass
class CompiledRule:
    id: str
    zone_id: str
    spec: RegisteredActionSpec


@dataclass
class RulesConfig:
    test_point: str = "foot"
    n_of_m: tuple[int, int] = (4, 5)
    min_confidence: float = 0.6
    hysteresis_drop: float = 0.1
    track_loss_tolerance_s: float = 1.5
    dwell_reset_after_s: float = 2.0
    timezone: str = "Asia/Kolkata"


class RuleEngine:
    """Pure rule evaluator."""

    def __init__(
        self,
        rules: list[CompiledRule],
        zones: dict[str, CompiledZone],
        cfg: RulesConfig | None = None
    ):
        self.rules = rules
        self.zones = zones
        self.cfg = cfg or RulesConfig()

        # Validate that rules are on special zones and templates match shapes
        for r in self.rules:
            z = self.zones.get(r.zone_id)
            if z:
                dummy_zone = ZoneSpec(
                    id=z.id,
                    name=z.name,
                    kind=z.kind, # type: ignore
                    shape=z.shape, # type: ignore
                    points=[list(p) for p in z.points],
                    direction=z.direction # type: ignore
                )
                validate_rule_zone_compatibility(r.spec, dummy_zone)

        # State tracking:
        # (rule_id, track_id) -> state dict
        self._track_states: dict[tuple[str, int], dict[str, Any]] = {}
        # rule_id -> count_threshold state
        self._count_states: dict[str, dict[str, Any]] = {}
        # (rule_id, track_id) -> last event end timestamp (for cooldown)
        self._cooldowns: dict[tuple[str, int], int] = {}
        # track_id -> previous foot point for line crossing
        self._prev_foot_points: dict[int, tuple[float, float]] = {}
        # rule_id -> list of past event timestamps (for escalation)
        self._recent_events: dict[str, list[int]] = {}

    def _get_pixel_points(self, zone: CompiledZone, frame_size: tuple[int, int]) -> list[tuple[float, float]]:
        """Ensure zone points are scaled to the frame dimensions."""
        w, h = frame_size
        pts = zone.points
        if not pts:
            return []
        is_normalized = all(0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0 for p in pts)
        if is_normalized and (w > 1 or h > 1):
            return denormalize_points(pts, w, h)
        return pts

    def _subject_matches_kind(self, kind: str, detected_cls: str) -> bool:
        """Check if detected class matches rule subject kind."""
        if kind == "vehicle":
            return detected_cls in ("car", "two_wheeler", "bus", "truck", "auto_rickshaw")
        elif kind == "person":
            return detected_cls == "person"
        return False

    def step(
        self,
        frame: TrackedFrame,
        attrs: dict[int, TrackAttributes],
        now_ms: int,
        exempt: Callable[[str, int], bool] | None = None
    ) -> list[Decision]:
        """Evaluate one frame tick against all compiled rules."""
        decisions: list[Decision] = []

        for rule in self.rules:
            zone = self.zones.get(rule.zone_id)
            if not zone:
                continue

            zone_pts = self._get_pixel_points(zone, frame.frame_size)
            if not zone_pts:
                continue

            armed = is_rule_armed(rule.spec, now_ms, exempt)
            template = rule.spec.trigger.template

            if template == "count_threshold":
                self._step_count_threshold(
                    rule, zone, zone_pts, frame, attrs, now_ms, armed, decisions
                )
            elif template == "line_crossing":
                if armed:
                    self._step_line_crossing(
                        rule, zone, zone_pts, frame, attrs, now_ms, decisions
                    )
            elif template in ("presence", "dwell"):
                self._step_polygon_track_rule(
                    rule, zone, zone_pts, frame, attrs, now_ms, armed, decisions
                )

        # Update previous foot points for line crossing
        for obj in frame.objects:
            self._prev_foot_points[obj.track_id] = obj.foot_point

        return decisions

    def _step_line_crossing(
        self,
        rule: CompiledRule,
        zone: CompiledZone,
        zone_pts: list[tuple[float, float]],
        frame: TrackedFrame,
        attrs: dict[int, TrackAttributes],
        now_ms: int,
        decisions: list[Decision]
    ) -> None:
        """Handle line crossing template."""
        if len(zone_pts) < 2:
            return
        p1, p2 = zone_pts[0], zone_pts[1]
        configured_dir = zone.direction or "in"

        for obj in frame.objects:
            prev_pt = self._prev_foot_points.get(obj.track_id)
            if prev_pt is None:
                continue

            curr_pt = obj.foot_point
            crossed, observed_dir = check_line_crossing(p1, p2, prev_pt, curr_pt, configured_dir)
            if not crossed:
                continue

            if not self._subject_matches_kind(rule.spec.subject.kind, obj.cls):
                continue

            box_h = obj.xyxy[3] - obj.xyxy[1]
            if rule.spec.subject.min_box_px and box_h < rule.spec.subject.min_box_px:
                continue

            track_attrs = attrs.get(obj.track_id)
            if not eval_where(rule.spec.subject.where, track_attrs):
                continue

            if obj.conf < rule.spec.confirm.min_confidence:
                continue

            # Check cooldown
            if (rule.id, obj.track_id) in self._cooldowns:
                last_end = self._cooldowns[(rule.id, obj.track_id)]
                cooldown_ms = int(rule.spec.response.cooldown_s * 1000)
                if now_ms - last_end < cooldown_ms:
                    continue

            # Escalation
            recent = self._recent_events.setdefault(rule.id, [])
            effective_sev = pick_severity(
                rule.spec.response.severity,
                rule.spec.response.escalation,
                recent,
                now_ms
            )

            snapshot = self._build_snapshot(obj, track_attrs)
            evidence = {
                "zone_id": zone.id,
                "zone_name": zone.name,
                "template": "line_crossing",
                "direction": observed_dir,
                "severity": effective_sev,
                "rule_name": rule.spec.name
            }

            decisions.append(Decision(
                kind="start",
                rule_id=rule.id,
                track_id=obj.track_id,
                ts_ms=now_ms,
                subject_snapshot=snapshot,
                confidence=obj.conf,
                evidence=evidence
            ))
            decisions.append(Decision(
                kind="end",
                rule_id=rule.id,
                track_id=obj.track_id,
                ts_ms=now_ms,
                subject_snapshot=snapshot,
                confidence=obj.conf,
                evidence=evidence
            ))

            recent.append(now_ms)
            self._cooldowns[(rule.id, obj.track_id)] = now_ms

    def _step_polygon_track_rule(
        self,
        rule: CompiledRule,
        zone: CompiledZone,
        zone_pts: list[tuple[float, float]],
        frame: TrackedFrame,
        attrs: dict[int, TrackAttributes],
        now_ms: int,
        armed: bool,
        decisions: list[Decision]
    ) -> None:
        """Handle presence and dwell rules for polygon zones."""
        template = rule.spec.trigger.template
        n_req, m_win = rule.spec.confirm.n_of_m[0], rule.spec.confirm.n_of_m[1]
        min_conf = rule.spec.confirm.min_confidence
        hysteresis_drop = self.cfg.hysteresis_drop

        active_track_ids = set()

        for obj in frame.objects:
            track_id = obj.track_id
            active_track_ids.add(track_id)
            state_key = (rule.id, track_id)

            if state_key not in self._track_states:
                self._track_states[state_key] = {
                    "history": [],
                    "confirmed": False,
                    "first_hold_ms": None,
                    "dwell_start_ms": None,
                    "last_in_zone_ms": None,
                    "active_event": False,
                    "last_seen_ms": now_ms,
                    "last_snapshot": None
                }
            st = self._track_states[state_key]
            st["last_seen_ms"] = now_ms

            # 1. Spatial check
            in_zone = point_in_polygon(obj.foot_point, zone_pts)
            if in_zone:
                st["last_in_zone_ms"] = now_ms

            # 2. Subject match
            kind_match = self._subject_matches_kind(rule.spec.subject.kind, obj.cls)
            box_h = obj.xyxy[3] - obj.xyxy[1]
            box_match = (rule.spec.subject.min_box_px is None or box_h >= rule.spec.subject.min_box_px)
            track_attrs = attrs.get(track_id)
            cond_match = eval_where(rule.spec.subject.where, track_attrs)

            holds = in_zone and kind_match and box_match and cond_match and armed

            if holds:
                if st["first_hold_ms"] is None:
                    st["first_hold_ms"] = now_ms

            # 3. Rolling confirmation window
            st["history"].append((holds, obj.conf, now_ms))
            if len(st["history"]) > m_win:
                st["history"].pop(0)

            # Count true ticks
            true_ticks = [c for h, c, t in st["history"] if h]
            num_true = len(true_ticks)
            mean_conf = (sum(true_ticks) / num_true) if num_true > 0 else 0.0

            if st["active_event"]:
                confirmed = (num_true >= n_req) and (mean_conf >= (min_conf - hysteresis_drop))
            else:
                confirmed = (num_true >= n_req) and (mean_conf >= min_conf)

            st["confirmed"] = confirmed

            # 4. Trigger evaluation
            if template == "presence":
                min_sec_ms = int(rule.spec.trigger.min_seconds * 1000)
                if confirmed and st["first_hold_ms"] is not None:
                    duration = now_ms - st["first_hold_ms"]
                    if duration >= min_sec_ms:
                        self._trigger_or_update_event(
                            rule, zone, obj, track_attrs, st, now_ms, mean_conf, decisions
                        )
                else:
                    if st["active_event"]:
                        self._end_event(rule, zone, track_id, st, now_ms, decisions)
                    if not in_zone:
                        st["first_hold_ms"] = None

            elif template == "dwell":
                dwell_target_ms = int((rule.spec.trigger.dwell_seconds or 0) * 1000)
                reset_after_ms = int(rule.spec.trigger.reset_after_s * 1000)

                if in_zone and confirmed:
                    if st["dwell_start_ms"] is None:
                        st["dwell_start_ms"] = now_ms
                    dwell_duration = now_ms - st["dwell_start_ms"]
                    if dwell_duration >= dwell_target_ms:
                        self._trigger_or_update_event(
                            rule, zone, obj, track_attrs, st, now_ms, mean_conf, decisions
                        )
                else:
                    last_in = st["last_in_zone_ms"] or 0
                    if now_ms - last_in > reset_after_ms:
                        if st["active_event"]:
                            self._end_event(rule, zone, track_id, st, now_ms, decisions)
                        st["dwell_start_ms"] = None

        # Handle tracks missing in this frame
        keys_to_remove = []
        track_loss_tol_ms = int(self.cfg.track_loss_tolerance_s * 1000)

        for (r_id, t_id), st in self._track_states.items():
            if r_id != rule.id:
                continue
            if t_id not in active_track_ids:
                # Add False to confirmation history
                st["history"].append((False, 0.0, now_ms))
                if len(st["history"]) > m_win:
                    st["history"].pop(0)

                # Check if confirmed dropped
                true_ticks = [c for h, c, t in st["history"] if h]
                if len(true_ticks) < n_req:
                    st["confirmed"] = False

                # Check track loss tolerance
                if now_ms - st["last_seen_ms"] > track_loss_tol_ms:
                    if st["active_event"]:
                        self._end_event(rule, zone, t_id, st, now_ms, decisions)
                    st["first_hold_ms"] = None
                    keys_to_remove.append((r_id, t_id))

        for k in keys_to_remove:
            self._track_states.pop(k, None)

    def _step_count_threshold(
        self,
        rule: CompiledRule,
        zone: CompiledZone,
        zone_pts: list[tuple[float, float]],
        frame: TrackedFrame,
        attrs: dict[int, TrackAttributes],
        now_ms: int,
        armed: bool,
        decisions: list[Decision]
    ) -> None:
        """Handle count_threshold template for polygon zones."""
        st = self._count_states.setdefault(rule.id, {
            "active_event": False,
            "threshold_start_ms": None,
            "last_seen_tracks": []
        })

        if not armed:
            if st["active_event"]:
                decisions.append(Decision(
                    kind="end",
                    rule_id=rule.id,
                    track_id=None,
                    ts_ms=now_ms,
                    subject_snapshot={"count": 0},
                    confidence=1.0,
                    evidence={"zone_id": zone.id, "zone_name": zone.name, "rule_name": rule.spec.name}
                ))
                st["active_event"] = False
            st["threshold_start_ms"] = None
            return

        target_count = rule.spec.trigger.count or 1
        min_sec_ms = int(rule.spec.trigger.min_seconds * 1000)

        matching_tracks = []
        for obj in frame.objects:
            if not self._subject_matches_kind(rule.spec.subject.kind, obj.cls):
                continue
            box_h = obj.xyxy[3] - obj.xyxy[1]
            if rule.spec.subject.min_box_px and box_h < rule.spec.subject.min_box_px:
                continue
            if not point_in_polygon(obj.foot_point, zone_pts):
                continue
            track_attrs = attrs.get(obj.track_id)
            if not eval_where(rule.spec.subject.where, track_attrs):
                continue
            matching_tracks.append(obj.track_id)

        curr_count = len(matching_tracks)
        st["last_seen_tracks"] = matching_tracks

        if curr_count >= target_count:
            if st["threshold_start_ms"] is None:
                st["threshold_start_ms"] = now_ms

            duration = now_ms - st["threshold_start_ms"]
            if duration >= min_sec_ms and not st["active_event"]:
                recent = self._recent_events.setdefault(rule.id, [])
                effective_sev = pick_severity(
                    rule.spec.response.severity,
                    rule.spec.response.escalation,
                    recent,
                    now_ms
                )
                evidence = {
                    "zone_id": zone.id,
                    "zone_name": zone.name,
                    "template": "count_threshold",
                    "count": curr_count,
                    "matching_tracks": matching_tracks,
                    "severity": effective_sev,
                    "rule_name": rule.spec.name
                }
                decisions.append(Decision(
                    kind="start",
                    rule_id=rule.id,
                    track_id=None,
                    ts_ms=now_ms,
                    subject_snapshot={"count": curr_count, "tracks": matching_tracks},
                    confidence=1.0,
                    evidence=evidence
                ))
                st["active_event"] = True
                recent.append(now_ms)
        else:
            if st["active_event"]:
                decisions.append(Decision(
                    kind="end",
                    rule_id=rule.id,
                    track_id=None,
                    ts_ms=now_ms,
                    subject_snapshot={"count": curr_count},
                    confidence=1.0,
                    evidence={"zone_id": zone.id, "zone_name": zone.name, "rule_name": rule.spec.name}
                ))
                st["active_event"] = False
            st["threshold_start_ms"] = None

    def _trigger_or_update_event(
        self,
        rule: CompiledRule,
        zone: CompiledZone,
        obj: TrackedObject,
        track_attrs: TrackAttributes | None,
        st: dict[str, Any],
        now_ms: int,
        confidence: float,
        decisions: list[Decision]
    ) -> None:
        """Helper to fire start or update decision for a track."""
        snapshot = self._build_snapshot(obj, track_attrs)

        if not st["active_event"]:
            # Check cooldown
            if (rule.id, obj.track_id) in self._cooldowns:
                last_end = self._cooldowns[(rule.id, obj.track_id)]
                cooldown_ms = int(rule.spec.response.cooldown_s * 1000)
                if now_ms - last_end < cooldown_ms:
                    return  # Cooldown active

            # Escalation
            recent = self._recent_events.setdefault(rule.id, [])
            effective_sev = pick_severity(
                rule.spec.response.severity,
                rule.spec.response.escalation,
                recent,
                now_ms
            )

            evidence = {
                "zone_id": zone.id,
                "zone_name": zone.name,
                "template": rule.spec.trigger.template,
                "severity": effective_sev,
                "rule_name": rule.spec.name
            }

            decisions.append(Decision(
                kind="start",
                rule_id=rule.id,
                track_id=obj.track_id,
                ts_ms=now_ms,
                subject_snapshot=snapshot,
                confidence=confidence,
                evidence=evidence
            ))
            st["active_event"] = True
            st["last_snapshot"] = snapshot
            recent.append(now_ms)

        else:
            # Check for late-binding or attribute changes
            if snapshot != st.get("last_snapshot"):
                decisions.append(Decision(
                    kind="update",
                    rule_id=rule.id,
                    track_id=obj.track_id,
                    ts_ms=now_ms,
                    subject_snapshot=snapshot,
                    confidence=confidence,
                    evidence={"zone_id": zone.id, "zone_name": zone.name, "rule_name": rule.spec.name}
                ))
                st["last_snapshot"] = snapshot

    def _end_event(
        self,
        rule: CompiledRule,
        zone: CompiledZone,
        track_id: int,
        st: dict[str, Any],
        now_ms: int,
        decisions: list[Decision]
    ) -> None:
        """Helper to fire end decision for an active event."""
        decisions.append(Decision(
            kind="end",
            rule_id=rule.id,
            track_id=track_id,
            ts_ms=now_ms,
            subject_snapshot=st.get("last_snapshot") or {},
            confidence=1.0,
            evidence={"zone_id": zone.id, "zone_name": zone.name, "rule_name": rule.spec.name}
        ))
        st["active_event"] = False
        st["first_hold_ms"] = None
        st["dwell_start_ms"] = None
        self._cooldowns[(rule.id, track_id)] = now_ms

    def _build_snapshot(self, obj: TrackedObject, track_attrs: TrackAttributes | None) -> dict[str, Any]:
        """Build serializable snapshot of the track state and attributes."""
        attrs_dict = {}
        if track_attrs:
            for k, v in track_attrs.attrs.items():
                attrs_dict[k] = {
                    "value": v.value,
                    "conf": v.conf,
                    "state": v.state
                }
        return {
            "track_id": obj.track_id,
            "cls": obj.cls,
            "conf": obj.conf,
            "xyxy": list(obj.xyxy),
            "foot_point": list(obj.foot_point),
            "attributes": attrs_dict
        }

    def flush(self, now_ms: int) -> list[Decision]:
        """End of stream: close any currently open events cleanly."""
        decisions: list[Decision] = []

        # Close polygon/track events
        for (rule_id, track_id), st in self._track_states.items():
            if st["active_event"]:
                rule = next((r for r in self.rules if r.id == rule_id), None)
                zone = self.zones.get(rule.zone_id) if rule else None
                decisions.append(Decision(
                    kind="end",
                    rule_id=rule_id,
                    track_id=track_id,
                    ts_ms=now_ms,
                    subject_snapshot=st.get("last_snapshot") or {},
                    confidence=1.0,
                    evidence={"zone_id": zone.id if zone else "", "flush": True}
                ))
                st["active_event"] = False

        # Close count_threshold events
        for rule_id, st in self._count_states.items():
            if st["active_event"]:
                decisions.append(Decision(
                    kind="end",
                    rule_id=rule_id,
                    track_id=None,
                    ts_ms=now_ms,
                    subject_snapshot={},
                    confidence=1.0,
                    evidence={"flush": True}
                ))
                st["active_event"] = False

        return decisions
