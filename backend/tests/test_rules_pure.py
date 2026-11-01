"""Pure Rule Engine and Attribute Store tests (docs/04 s8).

Zero GPU, zero network, zero DB. Fast and deterministic.
Verifies all conditions, schedule across midnight, escalation,
cooldown, N-of-M flicker tolerance, unknown never matches,
late-binding attributes, template applicability, and determinism.
"""

import os
import re
from datetime import datetime

import pytest

from app.attributes.store import AttributeStore
from app.core.types import AttrValue, TrackedFrame, TrackedObject
from app.rules.conditions import eval_condition
from app.rules.engine import CompiledRule, CompiledZone, RuleEngine
from app.rules.escalation import pick_severity
from app.rules.models import (
    ConditionSpec,
    ConfirmSpec,
    EscalationRow,
    ExemptionsSpec,
    RegisteredActionSpec,
    ResponseSpec,
    ScheduleSpec,
    SubjectSpec,
    TriggerSpec,
    ValidSpec,
    ZoneSpec,
    validate_rule_zone_compatibility,
)
from app.rules.schedule import is_in_schedule, is_in_valid_dates, is_rule_armed, resolve_timezone

# --- 1. Conditions and Attribute Store ---

def test_unknown_never_matches_any_condition():
    """Honesty Rule (AGENT_RULES 6b): unknown state NEVER matches any condition."""
    # Attribute is unknown
    attr_unknown = AttrValue(value="car", conf=0.0, state="unknown", n_obs=1, updated_ms=1000)

    # 1. eq
    c_eq = ConditionSpec(attr="category", op="eq", value="car")
    assert eval_condition(c_eq, attr_unknown) is False

    # 2. ne (CRITICAL: unknown must NOT match "not equal")
    c_ne = ConditionSpec(attr="category", op="ne", value="truck")
    assert eval_condition(c_ne, attr_unknown) is False

    # 3. in
    c_in = ConditionSpec(attr="category", op="in", value=["car", "truck"])
    assert eval_condition(c_in, attr_unknown) is False

    # 4. not_in (CRITICAL: unknown must NOT match "not in")
    c_not_in = ConditionSpec(attr="category", op="not_in", value=["truck"])
    assert eval_condition(c_not_in, attr_unknown) is False

    # 5. startswith
    c_sw = ConditionSpec(attr="plate", op="startswith", value="KA")
    assert eval_condition(c_sw, attr_unknown) is False

    # None attribute
    assert eval_condition(c_eq, None) is False


def test_condition_operators_known_state():
    attr_known = AttrValue(value="truck", conf=0.9, state="known", n_obs=3, updated_ms=1000)

    assert eval_condition(ConditionSpec(attr="category", op="eq", value="truck"), attr_known) is True
    assert eval_condition(ConditionSpec(attr="category", op="eq", value="car"), attr_known) is False
    assert eval_condition(ConditionSpec(attr="category", op="ne", value="car"), attr_known) is True
    assert eval_condition(ConditionSpec(attr="category", op="in", value=["truck", "bus"]), attr_known) is True
    assert eval_condition(ConditionSpec(attr="category", op="not_in", value=["car", "bike"]), attr_known) is True

    plate_attr = AttrValue(value="KA05AB1234", conf=0.95, state="known", n_obs=5, updated_ms=1000)
    assert eval_condition(ConditionSpec(attr="plate", op="startswith", value="KA05"), plate_attr) is True
    assert eval_condition(ConditionSpec(attr="plate", op="startswith", value="MH01"), plate_attr) is False


def test_attribute_store_operations():
    store = AttributeStore()
    track = store.set_attr(
        track_id=1,
        kind="vehicle",
        name="category",
        value="car",
        conf=0.85,
        state="known",
        ts_ms=1000
    )
    assert track.track_id == 1
    assert store.is_known(1, "category") is True
    assert store.get_known_value(1, "category") == "car"
    assert store.get_attr(1, "category").n_obs == 1

    # Update attribute: n_obs increments
    store.set_attr(1, "vehicle", "category", "car", 0.9, "known", 1040)
    assert store.get_attr(1, "category").n_obs == 2

    # Set unknown attribute
    store.set_attr(1, "vehicle", "plate", None, 0.0, "unknown", 1040)
    assert store.is_known(1, "plate") is False
    assert store.get_known_value(1, "plate") is None

    # Snapshot
    snap = store.snapshot(1)
    assert snap["category"]["value"] == "car"
    assert snap["plate"]["state"] == "unknown"


# --- 2. Schedules, Dates, and Calendar Exemptions ---

def test_schedule_day_of_week_and_time_window():
    # 2026-10-05 was a Monday. Let's make explicit timestamps.
    # 2026-10-05 10:00:00 Asia/Kolkata (+05:30)
    tz = resolve_timezone("Asia/Kolkata")
    dt_mon_10am = datetime(2026, 10, 5, 10, 0, 0, tzinfo=tz)
    ts_mon_10am = int(dt_mon_10am.timestamp() * 1000)

    # 1. Mon-Fri 09:00 - 17:00
    sched = ScheduleSpec(days=["mon", "tue", "wed", "thu", "fri"], from_time="09:00", to_time="17:00")
    assert is_in_schedule(sched, ts_mon_10am) is True

    # 2. Outside hours: Monday 18:00
    dt_mon_6pm = datetime(2026, 10, 5, 18, 0, 0, tzinfo=tz)
    ts_mon_6pm = int(dt_mon_6pm.timestamp() * 1000)
    assert is_in_schedule(sched, ts_mon_6pm) is False

    # 3. Outside day: Sunday 10:00 (2026-10-11)
    dt_sun_10am = datetime(2026, 10, 11, 10, 0, 0, tzinfo=tz)
    ts_sun_10am = int(dt_sun_10am.timestamp() * 1000)
    assert is_in_schedule(sched, ts_sun_10am) is False


def test_schedule_across_midnight():
    # Night shift: 22:00 to 04:00
    sched_night = ScheduleSpec(days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"], from_time="22:00", to_time="04:00")
    tz = resolve_timezone("Asia/Kolkata")

    # 23:30 (active)
    dt_2330 = datetime(2026, 10, 5, 23, 30, 0, tzinfo=tz)
    assert is_in_schedule(sched_night, int(dt_2330.timestamp() * 1000)) is True

    # 02:15 (active)
    dt_0215 = datetime(2026, 10, 6, 2, 15, 0, tzinfo=tz)
    assert is_in_schedule(sched_night, int(dt_0215.timestamp() * 1000)) is True

    # 12:00 noon (inactive)
    dt_noon = datetime(2026, 10, 6, 12, 0, 0, tzinfo=tz)
    assert is_in_schedule(sched_night, int(dt_noon.timestamp() * 1000)) is False


def test_valid_calendar_dates_and_exemptions():
    valid_spec = ValidSpec(from_date="2026-10-01", until_date="2026-10-31")
    tz = resolve_timezone("Asia/Kolkata")

    ts_inside = int(datetime(2026, 10, 15, 12, 0, 0, tzinfo=tz).timestamp() * 1000)
    ts_before = int(datetime(2026, 9, 30, 12, 0, 0, tzinfo=tz).timestamp() * 1000)
    ts_after = int(datetime(2026, 11, 1, 12, 0, 0, tzinfo=tz).timestamp() * 1000)

    assert is_in_valid_dates(valid_spec, ts_inside) is True
    assert is_in_valid_dates(valid_spec, ts_before) is False
    assert is_in_valid_dates(valid_spec, ts_after) is False

    # Full rule armed with exemption
    spec = RegisteredActionSpec(
        name="Test Rule",
        subject=SubjectSpec(kind="vehicle"),
        trigger=TriggerSpec(template="presence", min_seconds=0),
        exemptions=ExemptionsSpec(calendar_ids=["holiday_diwali"])
    )

    def dummy_exempt(cal_id: str, ts_ms: int) -> bool:
        return cal_id == "holiday_diwali" and ts_ms == ts_inside

    # When exempt date matches, rule is suppressed
    assert is_rule_armed(spec, ts_inside, exempt=dummy_exempt) is False
    assert is_rule_armed(spec, ts_inside + 100000, exempt=dummy_exempt) is True


# --- 3. Escalation and Severity ---

def test_escalation_pick_severity():
    rows = [
        EscalationRow(if_count_in_window={"n": 3, "window_min": 10}, severity="medium"),
        EscalationRow(if_count_in_window={"n": 5, "window_min": 10}, severity="critical"),
    ]

    now = 1000000
    # 0 events -> base low
    assert pick_severity("low", rows, [], now) == "low"

    # 3 events in 10 minutes -> medium
    events_3 = [now - 60000, now - 120000, now - 180000]
    assert pick_severity("low", rows, events_3, now) == "medium"

    # 5 events in 10 minutes -> critical
    events_5 = events_3 + [now - 240000, now - 300000]
    assert pick_severity("low", rows, events_5, now) == "critical"

    # Events outside window (> 10 min ago = > 600000 ms ago)
    old_events = [now - 700000, now - 800000, now - 900000]
    assert pick_severity("low", rows, old_events, now) == "low"


# --- 4. Validation Invariants ---

def test_normal_zone_rejects_actions():
    rule = RegisteredActionSpec(
        name="No trucks",
        subject=SubjectSpec(kind="vehicle"),
        trigger=TriggerSpec(template="presence", min_seconds=1)
    )
    normal_zone = ZoneSpec(
        id="z1",
        name="Normal Bay",
        kind="normal",
        shape="polygon",
        points=[[0, 0], [10, 0], [10, 10], [0, 10]]
    )
    with pytest.raises(ValueError, match="Cannot register an action on a 'normal' zone"):
        validate_rule_zone_compatibility(rule, normal_zone)


def test_template_shape_mismatch():
    line_rule = RegisteredActionSpec(
        name="Gate crossing",
        subject=SubjectSpec(kind="vehicle"),
        trigger=TriggerSpec(template="line_crossing")
    )
    poly_zone = ZoneSpec(
        id="z1",
        name="Special Bay",
        kind="special",
        shape="polygon",
        points=[[0, 0], [10, 0], [10, 10], [0, 10]]
    )
    with pytest.raises(ValueError, match="line_crossing.*requires a 'line' zone"):
        validate_rule_zone_compatibility(line_rule, poly_zone)

    presence_rule = RegisteredActionSpec(
        name="Presence check",
        subject=SubjectSpec(kind="vehicle"),
        trigger=TriggerSpec(template="presence")
    )
    line_zone = ZoneSpec(
        id="z2",
        name="Gate line",
        kind="special",
        shape="line",
        points=[[0, 0], [10, 10]]
    )
    with pytest.raises(ValueError, match="presence.*requires a 'polygon' zone"):
        validate_rule_zone_compatibility(presence_rule, line_zone)


# --- 5. Rule Engine Execution: Presence, Flicker, Cooldown, Late-Binding ---

def test_presence_rule_with_flicker_n_of_m():
    """Verify presence rule triggers and withstands 1-frame detector flicker."""
    zone = CompiledZone(
        id="z_special",
        name="Loading Bay",
        kind="special",
        shape="polygon",
        points=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    )
    rule = CompiledRule(
        id="r_truck",
        zone_id="z_special",
        spec=RegisteredActionSpec(
            name="Heavy truck in zone",
            subject=SubjectSpec(
                kind="vehicle",
                where=[ConditionSpec(attr="heavy", op="eq", value=True)]
            ),
            trigger=TriggerSpec(template="presence", min_seconds=0.2), # 200 ms
            confirm=ConfirmSpec(n_of_m=[4, 5], min_confidence=0.6),
            response=ResponseSpec(severity="critical", cooldown_s=10.0)
        )
    )

    engine = RuleEngine([rule], {"z_special": zone})
    attr_store = AttributeStore()
    attr_store.set_attr(1, "vehicle", "heavy", True, 0.9, "known", 1000)

    decisions = []
    # 5 frames at 40ms intervals (1000, 1040, 1080, 1120, 1160)
    # Frame 3 (1080) flickers: detector drops detection!
    # Frames:
    # 1: inside (holds)
    # 2: inside (holds)
    # 3: MISSING (flicker drop)
    # 4: inside (holds)
    # 5: inside (holds)
    # Total holds in window of 5 = 4. 4 >= 4 (N-of-M), duration = 160ms.
    # Frame 6 at 1200ms: inside (holds) -> duration 200ms reached! Event must fire!

    timestamps = [1000, 1040, 1080, 1120, 1160, 1200, 1240]
    for ts in timestamps:
        if ts == 1080:
            # Flicker drop: empty frame
            tf = TrackedFrame("cam1", ts, (100, 100), [])
        else:
            obj = TrackedObject(1, "truck", 0.9, (10, 10, 30, 30), (20.0, 30.0), ts)
            tf = TrackedFrame("cam1", ts, (100, 100), [obj])

        decisions.extend(engine.step(tf, attr_store.all_attrs(), ts))

    starts = [d for d in decisions if d.kind == "start"]
    assert len(starts) == 1
    assert starts[0].rule_id == "r_truck"
    assert starts[0].track_id == 1
    assert starts[0].evidence["severity"] == "critical"


def test_cooldown_suppression():
    """Verify cooldown suppresses re-alerting the same track."""
    zone = CompiledZone("z1", "Zone", "special", "polygon", [(0, 0), (100, 0), (100, 100), (0, 100)])
    rule = CompiledRule(
        "r1", "z1",
        RegisteredActionSpec(
            name="Quick Presence",
            subject=SubjectSpec(kind="vehicle"),
            trigger=TriggerSpec(template="presence", min_seconds=0),
            confirm=ConfirmSpec(n_of_m=[1, 1], min_confidence=0.5),
            response=ResponseSpec(severity="low", cooldown_s=5.0)  # 5 sec cooldown
        )
    )
    engine = RuleEngine([rule], {"z1": zone})
    attr_store = AttributeStore()

    # Event 1 starts at 1000
    obj = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 1000)
    tf1 = TrackedFrame("cam1", 1000, (100, 100), [obj])
    d1 = engine.step(tf1, attr_store.all_attrs(), 1000)
    assert any(d.kind == "start" for d in d1)

    # Object leaves at 2000 (ends event at 2000, cooldown starts until 7000)
    # Track lost tolerance is 1.5s, so at 4000 it is confirmed ended
    tf_empty = TrackedFrame("cam1", 4000, (100, 100), [])
    d2 = engine.step(tf_empty, attr_store.all_attrs(), 4000)
    assert any(d.kind == "end" for d in d2)

    # Object re-enters at 5000 (within 5s cooldown: 2000 + 5000 = 7000)
    obj_re = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 5000)
    tf_re = TrackedFrame("cam1", 5000, (100, 100), [obj_re])
    d3 = engine.step(tf_re, attr_store.all_attrs(), 5000)
    # Must NOT start because cooldown is active!
    assert not any(d.kind == "start" for d in d3)

    # Re-enters after cooldown expired (at 10000 > 7000)
    obj_after = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 10000)
    tf_after = TrackedFrame("cam1", 10000, (100, 100), [obj_after])
    d4 = engine.step(tf_after, attr_store.all_attrs(), 10000)
    assert any(d.kind == "start" for d in d4)


def test_late_binding_attribute():
    """Verify rule fires when an attribute transitions from unknown to known mid-track."""
    zone = CompiledZone("z1", "Zone", "special", "polygon", [(0, 0), (100, 0), (100, 100), (0, 100)])
    rule = CompiledRule(
        "r_unreg", "z1",
        RegisteredActionSpec(
            name="Unregistered vehicle",
            subject=SubjectSpec(
                kind="vehicle",
                where=[ConditionSpec(attr="registry_status", op="eq", value="unregistered")]
            ),
            trigger=TriggerSpec(template="presence", min_seconds=0),
            confirm=ConfirmSpec(n_of_m=[1, 1], min_confidence=0.5)
        )
    )
    engine = RuleEngine([rule], {"z1": zone})
    attr_store = AttributeStore()

    # Track 1 inside zone, but registry_status is unknown
    attr_store.set_attr(1, "vehicle", "registry_status", None, 0.0, "unknown", 1000)
    obj = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 1000)
    tf = TrackedFrame("cam1", 1000, (100, 100), [obj])

    d1 = engine.step(tf, attr_store.all_attrs(), 1000)
    assert len(d1) == 0  # Does not fire

    # At 2000ms: plate is read, registry_status resolves to 'unregistered' (known)!
    attr_store.set_attr(1, "vehicle", "registry_status", "unregistered", 0.95, "known", 2000)
    attr_store.set_attr(1, "vehicle", "plate", "KA05AB1234", 0.95, "known", 2000)

    obj2 = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 2000)
    tf2 = TrackedFrame("cam1", 2000, (100, 100), [obj2])
    d2 = engine.step(tf2, attr_store.all_attrs(), 2000)

    # Now it fires!
    starts = [d for d in d2 if d.kind == "start"]
    assert len(starts) == 1
    assert starts[0].track_id == 1
    assert starts[0].subject_snapshot["attributes"]["plate"]["value"] == "KA05AB1234"


def test_dwell_reset():
    """Verify dwell timer resets when object exits zone longer than reset_after_s."""
    zone = CompiledZone("z1", "Zone", "special", "polygon", [(0, 0), (100, 0), (100, 100), (0, 100)])
    rule = CompiledRule(
        "r_dwell", "z1",
        RegisteredActionSpec(
            name="Dwell 5s",
            subject=SubjectSpec(kind="vehicle"),
            trigger=TriggerSpec(template="dwell", dwell_seconds=5.0, reset_after_s=2.0),
            confirm=ConfirmSpec(n_of_m=[1, 1], min_confidence=0.5)
        )
    )
    engine = RuleEngine([rule], {"z1": zone})
    attr_store = AttributeStore()

    # Object enters at 1000, stays until 3000 (2s dwell, target is 5s)
    obj_in = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 1000)
    engine.step(TrackedFrame("cam1", 1000, (100, 100), [obj_in]), attr_store.all_attrs(), 1000)
    engine.step(TrackedFrame("cam1", 3000, (100, 100), [obj_in]), attr_store.all_attrs(), 3000)

    # Object leaves to outside (x=150) at 3100, stays outside until 6000 (outside duration = 2.9s > 2.0s reset)
    obj_out = TrackedObject(1, "car", 0.9, (150, 150, 160, 160), (155, 160), 3100)
    engine.step(TrackedFrame("cam1", 3100, (100, 100), [obj_out]), attr_store.all_attrs(), 3100)
    obj_out2 = TrackedObject(1, "car", 0.9, (150, 150, 160, 160), (155, 160), 6000)
    engine.step(TrackedFrame("cam1", 6000, (100, 100), [obj_out2]), attr_store.all_attrs(), 6000)

    # Object re-enters at 6100. Because outside > 2s, dwell timer reset!
    # It stays 3s until 9100. Target is 5s -> should NOT fire yet.
    obj_in2 = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 6100)
    engine.step(TrackedFrame("cam1", 6100, (100, 100), [obj_in2]), attr_store.all_attrs(), 6100)
    obj_in3 = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 9100)
    d = engine.step(TrackedFrame("cam1", 9100, (100, 100), [obj_in3]), attr_store.all_attrs(), 9100)
    assert not any(d.kind == "start" for d in d)

    # At 11200 (6100 + 5100ms > 5s dwell): it fires!
    obj_in4 = TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 11200)
    d2 = engine.step(TrackedFrame("cam1", 11200, (100, 100), [obj_in4]), attr_store.all_attrs(), 11200)
    assert any(d.kind == "start" for d in d2)


def test_count_threshold_template():
    """Verify count_threshold fires when N matching tracks are inside zone for min_seconds."""
    zone = CompiledZone("z1", "Zone", "special", "polygon", [(0, 0), (100, 0), (100, 100), (0, 100)])
    rule = CompiledRule(
        "r_count", "z1",
        RegisteredActionSpec(
            name="Crowd Count",
            subject=SubjectSpec(kind="person"),
            trigger=TriggerSpec(template="count_threshold", count=2, min_seconds=0.1)
        )
    )
    engine = RuleEngine([rule], {"z1": zone})
    attr_store = AttributeStore()

    p1 = TrackedObject(1, "person", 0.9, (10, 10, 20, 40), (15, 40), 1000)
    p2 = TrackedObject(2, "person", 0.9, (30, 10, 40, 40), (35, 40), 1000)

    # 1 person at 1000 -> count = 1 < 2 -> no event
    engine.step(TrackedFrame("cam1", 1000, (100, 100), [p1]), attr_store.all_attrs(), 1000)

    # 2 persons at 1100 -> count = 2 >= 2 -> timer starts
    engine.step(TrackedFrame("cam1", 1100, (100, 100), [p1, p2]), attr_store.all_attrs(), 1100)

    # 2 persons at 1250 -> duration 150ms >= 100ms -> fires start!
    d = engine.step(TrackedFrame("cam1", 1250, (100, 100), [p1, p2]), attr_store.all_attrs(), 1250)
    starts = [x for x in d if x.kind == "start"]
    assert len(starts) == 1
    assert starts[0].evidence["count"] == 2

    # 1 person leaves at 1300 -> count drops to 1 -> fires end!
    d2 = engine.step(TrackedFrame("cam1", 1300, (100, 100), [p1]), attr_store.all_attrs(), 1300)
    ends = [x for x in d2 if x.kind == "end"]
    assert len(ends) == 1


# --- 6. Determinism and Grep Tests ---

def test_engine_determinism():
    """Identical input sequence produces exact identical decisions."""
    zone = CompiledZone("z1", "Zone", "special", "polygon", [(0, 0), (100, 0), (100, 100), (0, 100)])
    rule = CompiledRule(
        "r1", "z1",
        RegisteredActionSpec(
            name="Det Rule",
            subject=SubjectSpec(kind="vehicle"),
            trigger=TriggerSpec(template="presence", min_seconds=0.1),
            confirm=ConfirmSpec(n_of_m=[2, 3], min_confidence=0.6)
        )
    )

    frames = [
        TrackedFrame("cam1", 1000, (100, 100), [TrackedObject(1, "car", 0.8, (10, 10, 20, 20), (15, 20), 1000)]),
        TrackedFrame("cam1", 1050, (100, 100), [TrackedObject(1, "car", 0.85, (10, 10, 20, 20), (15, 20), 1050)]),
        TrackedFrame("cam1", 1150, (100, 100), [TrackedObject(1, "car", 0.9, (10, 10, 20, 20), (15, 20), 1150)]),
    ]

    # Run 1
    e1 = RuleEngine([rule], {"z1": zone})
    res1 = []
    for f in frames:
        res1.extend(e1.step(f, {}, f.ts_ms))
    res1.extend(e1.flush(1200))

    # Run 2
    e2 = RuleEngine([rule], {"z1": zone})
    res2 = []
    for f in frames:
        res2.extend(e2.step(f, {}, f.ts_ms))
    res2.extend(e2.flush(1200))

    assert len(res1) == len(res2)
    for d1, d2 in zip(res1, res2):
        assert d1.kind == d2.kind
        assert d1.rule_id == d2.rule_id
        assert d1.ts_ms == d2.ts_ms
        assert d1.track_id == d2.track_id
        assert d1.confidence == d2.confidence


def test_grep_no_clocks_in_pure_packages():
    """docs/04 s8: Grep test confirming zero calls to time.time() or datetime.now() in pure packages."""
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    pure_dirs = [
        os.path.join(backend_dir, "app", "rules"),
        os.path.join(backend_dir, "app", "attributes"),
    ]

    pattern = re.compile(r"\b(time\.time|datetime\.now|datetime\.utcnow)\b")
    violations = []

    for pdir in pure_dirs:
        for root, _, files in os.walk(pdir):
            for file in files:
                if file.endswith(".py"):
                    fpath = os.path.join(root, file)
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line_no, line in enumerate(f, 1):
                            if pattern.search(line):
                                violations.append(f"{fpath}:{line_no} -> {line.strip()}")

    assert not violations, "Pure packages must not call clock functions! Found:\n" + "\n".join(violations)
