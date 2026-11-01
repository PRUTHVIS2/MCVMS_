"""Generate synthetic test videos and answer JSON files for rule engine verification.

Creates 6 synthetic test scenarios in tests/synthetic/:
1. heavy_truck_in_zone.mp4 & .json
2. flicker.mp4 & .json
3. line_crossing.mp4 & .json
4. dwell.mp4 & .json
5. count.mp4 & .json
6. schedule_boundary.mp4 & .json
"""

import json
import os
from pathlib import Path

import cv2
import numpy as np

SYNTHETIC_DIR = Path(__file__).resolve().parent


def create_mp4(filename: str, frames: list, fps: int = 25, width: int = 640, height: int = 360):
    filepath = SYNTHETIC_DIR / filename
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(filepath), fourcc, fps, (width, height))
    for f in frames:
        out.write(f)
    out.release()
    print(f"Generated {filepath} ({len(frames)} frames)")


def make_blank_frame(width=640, height=360):
    return np.ones((height, width, 3), dtype=np.uint8) * 50


def draw_box(frame, x, y, w, h, color):
    cv2.rectangle(frame, (int(x), int(y)), (int(x + w), int(y + h)), color, -1)


def generate_all():
    os.makedirs(SYNTHETIC_DIR, exist_ok=True)
    width, height = 640, 360
    fps = 25

    # Colors:
    # RED = (0, 0, 255) -> truck (heavy)
    # BLUE = (255, 0, 0) -> car
    # GREEN = (0, 255, 0) -> person
    COLOR_TRUCK = (0, 0, 255)
    COLOR_CAR = (255, 0, 0)

    # 1. heavy_truck_in_zone
    for i in range(125):
        f = make_blank_frame(width, height)
        if 25 <= i <= 100:
            # Truck inside zone: pos (300, 180), size (60, 40)
            draw_box(f, 300, 180, 60, 40, COLOR_TRUCK)
        elif i < 25:
            # Moving towards zone from left
            x = 50 + (i / 25.0) * 150
            draw_box(f, x, 180, 60, 40, COLOR_TRUCK)
        else:
            # Moving out to right
            x = 300 + ((i - 100) / 25.0) * 200
            draw_box(f, x, 180, 60, 40, COLOR_TRUCK)
        frames.append(f)
    create_mp4("heavy_truck_in_zone.mp4", frames, fps, width, height)

    answer_1 = {
        "clip": "heavy_truck_in_zone.mp4",
        "camera": "cam01",
        "synthetic": True,
        "source_start": "2026-10-05T10:00:00+05:30",
        "description": "Truck enters loading bay and stays 3s. Presence min_seconds=1.0.",
        "zones": [
            {
                "name": "Loading bay",
                "kind": "special",
                "shape": "polygon",
                "points": [[200, 100], [500, 100], [500, 300], [200, 300]]
            }
        ],
        "rules": [
            {
                "name": "Heavy vehicle in loading bay",
                "subject": {
                    "kind": "vehicle",
                    "where": [{"attr": "heavy", "op": "eq", "value": True}]
                },
                "trigger": {"template": "presence", "min_seconds": 1.0},
                "confirm": {"n_of_m": [4, 5], "min_confidence": 0.6},
                "schedule": {
                    "days": ["mon", "tue", "wed", "thu", "fri"],
                    "from": "09:00",
                    "to": "17:00",
                    "timezone": "Asia/Kolkata"
                },
                "response": {"severity": "critical", "cooldown_s": 30.0}
            }
        ],
        "expected_events": [
            {
                "rule": "Heavy vehicle in loading bay",
                "start_s": 2.0,
                "end_s": 4.0
            }
        ],
        "tolerance_s": 0.5
    }
    with open(SYNTHETIC_DIR / "heavy_truck_in_zone.json", "w") as f:
        json.dump(answer_1, f, indent=2)

    # 2. flicker
    # Same truck inside zone from frame 25 to 100, but frames 35, 45, 55 are blank (flicker)
    frames_flicker = []
    for i in range(125):
        f = make_blank_frame(width, height)
        if 25 <= i <= 100 and i not in (35, 45, 55):
            draw_box(f, 300, 180, 60, 40, COLOR_TRUCK)
        frames_flicker.append(f)
    create_mp4("flicker.mp4", frames_flicker, fps, width, height)

    answer_2 = dict(answer_1)
    answer_2["clip"] = "flicker.mp4"
    answer_2["description"] = "Truck with intermittent 1-frame drops absorbed by N-of-M."
    with open(SYNTHETIC_DIR / "flicker.json", "w") as f:
        json.dump(answer_2, f, indent=2)

    # 3. line_crossing
    # Car moves horizontally from x=100 to x=540 across x=320 at frame 50 (2.0s)
    frames_line = []
    for i in range(100): # 4 seconds
        f = make_blank_frame(width, height)
        # x goes from 100 to 540 over 100 frames
        x = 100 + (i / 100.0) * 440
        y = 160
        draw_box(f, x, y, 40, 40, COLOR_CAR)
        frames_line.append(f)
    create_mp4("line_crossing.mp4", frames_line, fps, width, height)

    answer_3 = {
        "clip": "line_crossing.mp4",
        "camera": "cam01",
        "synthetic": True,
        "source_start": "2026-10-05T10:00:00+05:30",
        "description": "Car crosses vertical line at x=320 moving left to right (in).",
        "zones": [
            {
                "name": "Gate Line",
                "kind": "special",
                "shape": "line",
                "points": [[320, 310], [320, 50]],
                "direction": "in"
            }
        ],
        "rules": [
            {
                "name": "Vehicle enters gate",
                "subject": {"kind": "vehicle"},
                "trigger": {"template": "line_crossing"},
                "confirm": {"n_of_m": [1, 1], "min_confidence": 0.6},
                "response": {"severity": "low"}
            }
        ],
        "expected_events": [
            {
                "rule": "Vehicle enters gate",
                "start_s": 2.0
            }
        ],
        "tolerance_s": 0.5
    }
    with open(SYNTHETIC_DIR / "line_crossing.json", "w") as f:
        json.dump(answer_3, f, indent=2)

    # 4. dwell
    # Car enters zone at frame 25 (1.0s), stays until frame 150 (6.0s). Dwell 3.0s -> fires at 4.0s.
    frames_dwell = []
    for i in range(160): # 6.4 seconds
        f = make_blank_frame(width, height)
        if 25 <= i <= 150:
            draw_box(f, 320, 180, 40, 40, COLOR_CAR)
        frames_dwell.append(f)
    create_mp4("dwell.mp4", frames_dwell, fps, width, height)

    answer_4 = {
        "clip": "dwell.mp4",
        "camera": "cam01",
        "synthetic": True,
        "source_start": "2026-10-05T10:00:00+05:30",
        "description": "Car dwells in zone for 5s with dwell threshold of 3s.",
        "zones": [
            {
                "name": "No Parking Zone",
                "kind": "special",
                "shape": "polygon",
                "points": [[200, 100], [500, 100], [500, 300], [200, 300]]
            }
        ],
        "rules": [
            {
                "name": "Vehicle stays too long",
                "subject": {"kind": "vehicle"},
                "trigger": {"template": "dwell", "dwell_seconds": 3.0, "reset_after_s": 2.0},
                "confirm": {"n_of_m": [2, 3], "min_confidence": 0.6},
                "response": {"severity": "medium"}
            }
        ],
        "expected_events": [
            {
                "rule": "Vehicle stays too long",
                "start_s": 4.0
            }
        ],
        "tolerance_s": 0.5
    }
    with open(SYNTHETIC_DIR / "dwell.json", "w") as f:
        json.dump(answer_4, f, indent=2)

    # 5. count
    # Car 1 enters at frame 25 (1.0s). Car 2 enters at frame 50 (2.0s). Both stay until frame 125 (5.0s).
    # Count threshold: 2 cars for min_seconds=1.0s -> fires at 3.0s!
    frames_count = []
    for i in range(130):
        f = make_blank_frame(width, height)
        if i >= 25:
            draw_box(f, 250, 180, 40, 40, COLOR_CAR)
        if i >= 50:
            draw_box(f, 400, 180, 40, 40, COLOR_CAR)
        frames_count.append(f)
    create_mp4("count.mp4", frames_count, fps, width, height)

    answer_5 = {
        "clip": "count.mp4",
        "camera": "cam01",
        "synthetic": True,
        "source_start": "2026-10-05T10:00:00+05:30",
        "description": "Count threshold of 2 cars inside zone for 1.0s.",
        "zones": [
            {
                "name": "Courtyard",
                "kind": "special",
                "shape": "polygon",
                "points": [[100, 50], [550, 50], [550, 320], [100, 320]]
            }
        ],
        "rules": [
            {
                "name": "Vehicle congestion",
                "subject": {"kind": "vehicle"},
                "trigger": {"template": "count_threshold", "count": 2, "min_seconds": 1.0},
                "response": {"severity": "low"}
            }
        ],
        "expected_events": [
            {
                "rule": "Vehicle congestion",
                "start_s": 3.0
            }
        ],
        "tolerance_s": 0.5
    }
    with open(SYNTHETIC_DIR / "count.json", "w") as f:
        json.dump(answer_5, f, indent=2)

    # 6. schedule_boundary
    # Same truck inside zone from 1.0s to 4.0s, but source_start is 20:00 (8:00 PM), outside 09:00-17:00 schedule!
    create_mp4("schedule_boundary.mp4", frames, fps, width, height)
    answer_6 = dict(answer_1)
    answer_6["clip"] = "schedule_boundary.mp4"
    answer_6["source_start"] = "2026-10-05T20:00:00+05:30"
    answer_6["description"] = "Truck enters zone outside scheduled hours. Expected 0 events."
    answer_6["expected_events"] = []
    with open(SYNTHETIC_DIR / "schedule_boundary.json", "w") as f:
        json.dump(answer_6, f, indent=2)

    print("All synthetic clips and answer files generated successfully.")


if __name__ == "__main__":
    generate_all()
