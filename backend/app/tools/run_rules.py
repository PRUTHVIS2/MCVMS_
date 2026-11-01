"""Batch rule evaluation against ground-truth answer JSONs.

docs/04 s7:
python -m app.tools.run_rules --clip test_data/events/x.mp4 --answer test_data/events/x.json
Runs batch analysis and compares decisions with the answer file.
Prints PASS/FAIL per clip with a diff.
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from app.attributes.store import AttributeStore
from app.core.geometry import denormalize_points
from app.rules.engine import CompiledRule, CompiledZone, Decision, RuleEngine
from app.rules.models import RegisteredActionSpec
from app.sources.filesource import FileSource
from app.sources.timesource import FileTimeSource
from app.vision.detector import Detector
from app.vision.tracker import Tracker


def parse_iso_to_epoch_ms(iso_str: str) -> int:
    """Parse ISO 8601 string to integer epoch milliseconds."""
    dt = datetime.fromisoformat(iso_str)
    return int(dt.timestamp() * 1000)


def load_answer_file(json_path: str) -> dict[str, Any]:
    """Load and parse the answer file."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_compiled_zones_and_rules(
    answer: dict[str, Any],
    frame_width: int,
    frame_height: int
) -> tuple[dict[str, CompiledZone], list[CompiledRule]]:
    """Build CompiledZone and CompiledRule structures from the answer JSON."""
    compiled_zones: dict[str, CompiledZone] = {}
    special_zone_ids: list[str] = []

    for i, z_raw in enumerate(answer.get("zones", [])):
        z_id = f"zone_{i}"
        pts_raw = z_raw.get("points")
        if pts_raw is None:
            # Placeholder in unpopulated template
            pts = []
        else:
            # Check if normalized or pixel
            pts = [(float(p[0]), float(p[1])) for p in pts_raw]
            is_normalized = all(0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0 for p in pts)
            if is_normalized and (frame_width > 1 or frame_height > 1):
                pts = denormalize_points(pts, frame_width, frame_height)

        cz = CompiledZone(
            id=z_id,
            name=z_raw["name"],
            kind=z_raw["kind"],
            shape=z_raw["shape"],
            points=pts,
            direction=z_raw.get("direction"),
            is_read_area=bool(z_raw.get("is_read_area", False))
        )
        compiled_zones[z_id] = cz
        if cz.kind == "special":
            special_zone_ids.append(z_id)

    compiled_rules: list[CompiledRule] = []
    for j, r_raw in enumerate(answer.get("rules", [])):
        spec = RegisteredActionSpec(**r_raw)
        # Match rule to zone
        # Per docs/04 s7: first rule -> first special zone, unless a zone name key is given
        target_zone_id: str | None = None
        if "zone" in r_raw:
            for zid, cz in compiled_zones.items():
                if cz.name == r_raw["zone"]:
                    target_zone_id = zid
                    break
        if target_zone_id is None:
            if j < len(special_zone_ids):
                target_zone_id = special_zone_ids[j]
            elif special_zone_ids:
                target_zone_id = special_zone_ids[0]
            else:
                target_zone_id = "zone_special_fallback"

        compiled_rules.append(CompiledRule(
            id=f"rule_{j}",
            zone_id=target_zone_id or "zone_0",
            spec=spec
        ))

    return compiled_zones, compiled_rules


def evaluate_clip(
    clip_path: str,
    answer_path: str,
    detector: Any | None = None,
    tracker: Any | None = None
) -> tuple[bool, str, list[Decision]]:
    """Run batch analysis on a clip and compare against the answer file.
    
    Returns:
        (passed: bool, report: str, decisions: list[Decision])
    """
    answer = load_answer_file(answer_path)
    source_start_ms = parse_iso_to_epoch_ms(answer["source_start"])
    tolerance_s = float(answer.get("tolerance_s", 2.0))

    # Initialize frame and time sources
    time_source = FileTimeSource(source_start_ms)
    file_source = FileSource(clip_path, time_source, paced=False)

    w = int(file_source.width) or 1920
    h = int(file_source.height) or 1080

    zones, rules = build_compiled_zones_and_rules(answer, w, h)
    engine = RuleEngine(rules, zones)
    attr_store = AttributeStore()

    if detector is not None:
        det = detector
    elif answer.get("synthetic", False):
        from app.vision.synthetic_detector import SyntheticBoxDetector
        det = SyntheticBoxDetector()
    else:
        det = Detector()
    trk = tracker or Tracker(fps=int(file_source.fps) or 25)

    all_decisions: list[Decision] = []
    last_ts_ms = source_start_ms

    for frame, ts_ms in file_source.iter_frames():
        last_ts_ms = ts_ms
        detections = det.detect(frame)
        tracked_objects = trk.update(detections, frame, ts_ms)

        from app.core.types import TrackedFrame
        tracked_frame = TrackedFrame(
            camera_id=answer.get("camera", "cam01"),
            ts_ms=ts_ms,
            frame_size=(w, h),
            objects=tracked_objects
        )

        # Baseline attribute resolver: set category and heavy status for vehicles
        for obj in tracked_objects:
            kind = "person" if obj.cls == "person" else "vehicle"
            attr_store.set_attr(
                track_id=obj.track_id,
                kind=kind,
                name="category",
                value=obj.cls,
                conf=obj.conf,
                state="known",
                ts_ms=ts_ms
            )
            is_heavy = obj.cls in ("truck", "bus")
            attr_store.set_attr(
                track_id=obj.track_id,
                kind=kind,
                name="heavy",
                value=is_heavy,
                conf=obj.conf,
                state="known",
                ts_ms=ts_ms
            )

        new_decisions = engine.step(tracked_frame, attr_store.all_attrs(), ts_ms)
        all_decisions.extend(new_decisions)

    # Flush end of clip
    all_decisions.extend(engine.flush(last_ts_ms))

    # Filter to start decisions
    actual_starts = [d for d in all_decisions if d.kind == "start"]
    expected_events = answer.get("expected_events", [])

    # Map actual starts to seconds from start
    actual_with_times = []
    for d in actual_starts:
        rule_name = d.evidence.get("rule_name", "")
        start_s = (d.ts_ms - source_start_ms) / 1000.0
        actual_with_times.append({
            "rule": rule_name,
            "start_s": start_s,
            "decision": d
        })

    # Compare actual vs expected
    matched_expected = set()
    matched_actual = set()
    diff_lines = []

    for i, exp in enumerate(expected_events):
        exp_rule = exp.get("rule")
        exp_start = exp.get("start_s")
        if exp_start is None:
            continue

        best_match_idx = None
        min_diff = float("inf")

        for j, act in enumerate(actual_with_times):
            if j in matched_actual:
                continue
            if act["rule"] == exp_rule or not exp_rule:
                diff = abs(act["start_s"] - exp_start)
                if diff <= tolerance_s and diff < min_diff:
                    min_diff = diff
                    best_match_idx = j

        if best_match_idx is not None:
            matched_expected.add(i)
            matched_actual.add(best_match_idx)
            act = actual_with_times[best_match_idx]
            diff_lines.append(
                f"  MATCH: Rule='{exp_rule}' Expected={exp_start:.2f}s Actual={act['start_s']:.2f}s Diff={min_diff:.2f}s"
            )
        else:
            diff_lines.append(
                f"  MISSING (False Negative): Rule='{exp_rule}' Expected={exp_start:.2f}s"
            )

    for j, act in enumerate(actual_with_times):
        if j not in matched_actual:
            diff_lines.append(
                f"  UNEXPECTED (False Positive): Rule='{act['rule']}' Actual={act['start_s']:.2f}s"
            )

    passed = (len(matched_expected) == len([e for e in expected_events if e.get("start_s") is not None])
              and len(matched_actual) == len(actual_with_times))

    report = (
        f"\n============================================================\n"
        f"Clip:   {clip_path}\n"
        f"Answer: {answer_path}\n"
        f"Result: {'PASS' if passed else 'FAIL'}\n"
        f"Expected: {len(expected_events)} | Actual: {len(actual_with_times)}\n"
        f"Details:\n" + "\n".join(diff_lines) +
        "\n============================================================\n"
    )

    return passed, report, all_decisions


def main():
    parser = argparse.ArgumentParser(description="Evaluate video clip against rule engine answer JSON")
    parser.add_argument("--clip", required=True, help="Path to input MP4 video clip")
    parser.add_argument("--answer", required=True, help="Path to answer JSON file")
    args = parser.parse_args()

    passed, report, _ = evaluate_clip(args.clip, args.answer)
    print(report)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
