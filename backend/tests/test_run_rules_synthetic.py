"""Integration tests running run_rules across all synthetic clips and answer files.

docs/04 s7 & PLAN.md Step 4:
Ship generated synthetic clips + answers in tests/synthetic/
(heavy-truck-in-zone, flicker, line crossing, dwell, count, schedule boundary)
and run them through run_rules.
Zero mismatches required.
"""

from pathlib import Path

from app.tools.run_rules import evaluate_clip

SYNTHETIC_DIR = Path(__file__).resolve().parent / "synthetic"


def test_synthetic_heavy_truck_in_zone():
    clip = str(SYNTHETIC_DIR / "heavy_truck_in_zone.mp4")
    answer = str(SYNTHETIC_DIR / "heavy_truck_in_zone.json")
    passed, report, _ = evaluate_clip(clip, answer)
    print(report)
    assert passed is True, f"Failed heavy_truck_in_zone:\n{report}"


def test_synthetic_flicker_presence():
    clip = str(SYNTHETIC_DIR / "flicker.mp4")
    answer = str(SYNTHETIC_DIR / "flicker.json")
    passed, report, _ = evaluate_clip(clip, answer)
    print(report)
    assert passed is True, f"Failed flicker:\n{report}"


def test_synthetic_line_crossing():
    clip = str(SYNTHETIC_DIR / "line_crossing.mp4")
    answer = str(SYNTHETIC_DIR / "line_crossing.json")
    passed, report, _ = evaluate_clip(clip, answer)
    print(report)
    assert passed is True, f"Failed line_crossing:\n{report}"


def test_synthetic_dwell():
    clip = str(SYNTHETIC_DIR / "dwell.mp4")
    answer = str(SYNTHETIC_DIR / "dwell.json")
    passed, report, _ = evaluate_clip(clip, answer)
    print(report)
    assert passed is True, f"Failed dwell:\n{report}"


def test_synthetic_count_threshold():
    clip = str(SYNTHETIC_DIR / "count.mp4")
    answer = str(SYNTHETIC_DIR / "count.json")
    passed, report, _ = evaluate_clip(clip, answer)
    print(report)
    assert passed is True, f"Failed count:\n{report}"


def test_synthetic_schedule_boundary():
    clip = str(SYNTHETIC_DIR / "schedule_boundary.mp4")
    answer = str(SYNTHETIC_DIR / "schedule_boundary.json")
    passed, report, _ = evaluate_clip(clip, answer)
    print(report)
    assert passed is True, f"Failed schedule_boundary:\n{report}"
