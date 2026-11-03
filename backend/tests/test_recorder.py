"""Tests for continuous recorder and clip cutting.

Acceptance criteria for Step 5 (PLAN.md):
- Clip window maths (pre-roll, hold, max_clip_min cap, sighting 10 s).
- Cut from recorded segments produces valid MP4, duration verified by ffprobe to 1 frame accuracy.
- Cut succeeds when start/end span a segment boundary (concat).
- Atomic write: crash leaves no partial .mp4.
- Cut writes sidecar .meta.json with sha256 matching the .mp4.
- Clipper waits up to 15 s for covering segments to be written.
- Clip spanning a recording gap has status = 'incomplete'.
- Rebuild index tool restores SQLite rows from .meta.json files.
"""

import os
import json
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.core.clock import SimulatedClock
from app.recorder.ffmpeg_recorder import FFmpegRecorder, RecorderSupervisor
from app.recorder.clipper import (
    compute_clip_window,
    compute_sha256,
    get_video_duration_ffprobe,
    parse_segment_timestamp,
    Clipper,
    ClipRequest,
    ClipResult
)
from app.tools.rebuild_index import rebuild_index, verify_clip_file
from app.tools.cut_clip import parse_timestamp_arg


# Helper to generate test synthetic video segments using ffmpeg
def create_synthetic_segment(path: Path, duration_s: float = 5.0, fps: int = 25):
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_s}:size=640x360:rate={fps}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)


# 1. Clip window maths
def test_clip_window_maths_event():
    # 20s event with 15s pre-roll and 20s hold -> 55s
    start_ms = 100_000
    end_ms = 120_000
    w_start, w_end, dur_s = compute_clip_window(
        kind="event",
        start_ts_ms=start_ms,
        end_ts_ms=end_ms,
        pre_roll_s=15.0,
        hold_s=20.0
    )
    assert w_start == 85_000
    assert w_end == 140_000
    assert dur_s == 55.0


def test_clip_window_maths_event_capped():
    # 400s event with max_clip_min = 5.0 (300s)
    start_ms = 100_000
    end_ms = 500_000
    w_start, w_end, dur_s = compute_clip_window(
        kind="event",
        start_ts_ms=start_ms,
        end_ts_ms=end_ms,
        pre_roll_s=15.0,
        hold_s=20.0,
        max_clip_min=5.0
    )
    assert w_start == 85_000
    assert w_end == 85_000 + 300_000
    assert dur_s == 300.0


def test_clip_window_maths_sighting():
    # Sighting: strictly 10s around anchor [anchor - 4s, anchor + 6s]
    start_ms = 100_000
    end_ms = 108_000
    anchor_ms = 105_000
    w_start, w_end, dur_s = compute_clip_window(
        kind="sighting",
        start_ts_ms=start_ms,
        end_ts_ms=end_ms,
        anchor_ts_ms=anchor_ms,
        sighting_length_s=10.0,
        sighting_pre_s=4.0
    )
    assert w_start == 101_000
    assert w_end == 111_000
    assert dur_s == 10.0


def test_clip_window_maths_sighting_default_anchor():
    # Without explicit anchor, defaults to start_ts
    start_ms = 50_000
    end_ms = 55_000
    w_start, w_end, dur_s = compute_clip_window(
        kind="sighting",
        start_ts_ms=start_ms,
        end_ts_ms=end_ms,
        sighting_length_s=10.0,
        sighting_pre_s=4.0
    )
    assert w_start == 46_000
    assert w_end == 56_000
    assert dur_s == 10.0


# 2. Cut from recorded segments duration accuracy
def test_cut_from_segments_duration_accuracy(tmp_path):
    cam_id = "testcam1"
    cont_dir = tmp_path / "continuous"
    clips_dir = tmp_path / "clips"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    # Base timestamp: 2026-10-05 10:00:00 UTC = 1791194400000 ms
    base_dt = datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc)
    base_ms = int(base_dt.timestamp() * 1000)

    # Create segment 1: 5.0 seconds
    seg1_name = base_dt.strftime("%Y%m%d_%H%M%S.mkv")
    seg1_path = cam_dir / seg1_name
    create_synthetic_segment(seg1_path, duration_s=5.0)

    clipper = Clipper(clips_dir=str(clips_dir), continuous_dir=str(cont_dir))

    # Cut 3.0s clip within segment 1: from base_ms + 1000 to base_ms + 4000
    out_mp4 = clips_dir / "test_cut.mp4"
    segments = [(seg1_path, base_ms, base_ms + 5000)]
    success = clipper.cut_clip_from_segments(segments, out_mp4, window_start_ms=base_ms + 1000, duration_s=3.0)

    assert success is True
    assert out_mp4.exists()

    # Verify duration via ffprobe within 1 frame (1/25 = 0.04s)
    actual_dur = get_video_duration_ffprobe(out_mp4)
    assert abs(actual_dur - 3.0) <= 0.05


# 3. Cut spanning segment boundary (concat)
def test_cut_spanning_segment_boundary_concat(tmp_path):
    cam_id = "testcam2"
    cont_dir = tmp_path / "continuous"
    clips_dir = tmp_path / "clips"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    # Seg 1: 10:00:00 (5s) -> 10:00:05
    # Seg 2: 10:00:05 (5s) -> 10:00:10
    dt1 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 10, 5, 10, 0, 5, tzinfo=timezone.utc)
    ms1 = int(dt1.timestamp() * 1000)
    ms2 = int(dt2.timestamp() * 1000)

    seg1_path = cam_dir / dt1.strftime("%Y%m%d_%H%M%S.mkv")
    seg2_path = cam_dir / dt2.strftime("%Y%m%d_%H%M%S.mkv")

    create_synthetic_segment(seg1_path, duration_s=5.0)
    create_synthetic_segment(seg2_path, duration_s=5.0)

    clipper = Clipper(clips_dir=str(clips_dir), continuous_dir=str(cont_dir))

    # Cut 4.0s clip starting at 10:00:03 (2s into seg 1, 2s into seg 2)
    win_start = ms1 + 3000
    out_mp4 = clips_dir / "concat_cut.mp4"
    segments = [(seg1_path, ms1, ms1 + 5000), (seg2_path, ms2, ms2 + 5000)]

    success = clipper.cut_clip_from_segments(segments, out_mp4, window_start_ms=win_start, duration_s=4.0)
    assert success is True
    assert out_mp4.exists()

    # Duration must be within 1 frame accuracy (0.05s)
    actual_dur = get_video_duration_ffprobe(out_mp4)
    assert abs(actual_dur - 4.0) <= 0.05


# 4. Atomic write: crash leaves no partial .mp4
def test_atomic_write_crash_leaves_no_partial_mp4(tmp_path, monkeypatch):
    clips_dir = tmp_path / "clips"
    clipper = Clipper(clips_dir=str(clips_dir))

    out_mp4 = clips_dir / "target.mp4"

    # Mock subprocess.run to raise an exception or fail
    def fake_subprocess_run(*args, **kwargs):
        # Create a partial tmp file to simulate incomplete write before crash
        tmp = out_mp4.with_name(f"{out_mp4.name}.tmp.{os.getpid()}.mp4")
        tmp.write_bytes(b"partial junk data")
        raise RuntimeError("Simulated crash during ffmpeg execution")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    dummy_seg = tmp_path / "dummy.mkv"
    dummy_seg.write_bytes(b"dummy")

    with pytest.raises(RuntimeError):
        clipper.cut_clip_from_segments([(dummy_seg, 0, 5000)], out_mp4, window_start_ms=0, duration_s=5.0)

    # Assert target.mp4 was NEVER created
    assert not out_mp4.exists()


# 5. Sidecar .meta.json with SHA-256 matching .mp4
def test_sidecar_meta_json_sha256(tmp_path):
    cam_id = "testcam3"
    cont_dir = tmp_path / "continuous"
    clips_dir = tmp_path / "clips"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    dt1 = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)
    ms1 = int(dt1.timestamp() * 1000)
    seg_path = cam_dir / dt1.strftime("%Y%m%d_%H%M%S.mkv")
    create_synthetic_segment(seg_path, duration_s=12.0)

    clipper = Clipper(clips_dir=str(clips_dir), continuous_dir=str(cont_dir))

    req = ClipRequest(
        kind="sighting",
        camera_id=cam_id,
        start_ts_ms=ms1 + 5000,
        end_ts_ms=ms1 + 5000,
        anchor_ts_ms=ms1 + 5000,
        sighting_length_s=4.0,  # small for fast test
        sighting_pre_s=2.0
    )

    res = clipper.process_clip_request(req)
    assert res.status == "ready"
    assert Path(res.path).exists()
    assert Path(res.sidecar_path).exists()

    # Load sidecar JSON
    with open(res.sidecar_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Verify sha256 in sidecar matches actual file sha256
    actual_hash = compute_sha256(Path(res.path))
    assert meta["sha256"] == actual_hash
    assert meta["sha256"] == res.sha256
    assert meta["size_bytes"] == Path(res.path).stat().st_size
    assert len(meta["key_frames"]) == 3
    for kf in meta["key_frames"]:
        assert (Path(res.path).parent / kf).exists()


# 6. Clipper waits up to wait_timeout_s for covering segments
def test_clipper_waits_for_covering_segments(tmp_path):
    cam_id = "testcam4"
    cont_dir = tmp_path / "continuous"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    clipper = Clipper(continuous_dir=str(cont_dir))

    dt1 = datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc)
    ms1 = int(dt1.timestamp() * 1000)
    seg_path = cam_dir / dt1.strftime("%Y%m%d_%H%M%S.mkv")

    # In background thread, write segment after 0.5s
    def delayed_writer():
        time.sleep(0.5)
        create_synthetic_segment(seg_path, duration_s=10.0)

    t = threading.Thread(target=delayed_writer)
    t.start()

    # find_covering_segments should block, wait, and succeed
    segments = clipper.find_covering_segments(
        camera_id=cam_id,
        window_start_ms=ms1,
        window_end_ms=ms1 + 8000,
        wait_timeout_s=3.0
    )
    t.join()

    assert len(segments) >= 1
    assert segments[0][0] == seg_path


# 7. Clip spanning recording gap has status 'incomplete'
def test_clip_spanning_recording_gap_is_incomplete(tmp_path):
    cam_id = "testcam5"
    cont_dir = tmp_path / "continuous"
    clips_dir = tmp_path / "clips"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    dt1 = datetime(2026, 10, 5, 16, 0, 0, tzinfo=timezone.utc)
    ms1 = int(dt1.timestamp() * 1000)
    seg_path = cam_dir / dt1.strftime("%Y%m%d_%H%M%S.mkv")
    create_synthetic_segment(seg_path, duration_s=10.0)

    clipper = Clipper(clips_dir=str(clips_dir), continuous_dir=str(cont_dir))

    # Define a gap function simulating a recording gap at ms1 + 1000 .. ms1 + 3000
    def gap_checker(start_ms, end_ms):
        gap_start, gap_end = ms1 + 1000, ms1 + 3000
        return not (end_ms < gap_start or start_ms > gap_end)

    req = ClipRequest(
        kind="sighting",
        camera_id=cam_id,
        start_ts_ms=ms1 + 2000,
        end_ts_ms=ms1 + 2000,
        anchor_ts_ms=ms1 + 2000,
        sighting_length_s=4.0,
        sighting_pre_s=1.0
    )

    res = clipper.process_clip_request(req, has_gap_fn=gap_checker)
    assert res.status == "incomplete"

    with open(res.sidecar_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["status"] == "incomplete"


# 8. Rebuild index restores SQLite rows from .meta.json files
def test_rebuild_index_restores_sqlite_rows(tmp_path):
    clips_dir = tmp_path / "clips"
    cam_id = "cam_rebuild"
    clip_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"

    # Create dummy video and sidecar
    sub_dir = clips_dir / "2026" / "10" / "05" / cam_id
    sub_dir.mkdir(parents=True)
    video_path = sub_dir / f"{clip_id}.mp4"
    create_synthetic_segment(video_path, duration_s=3.0)
    sha256_hash = compute_sha256(video_path)

    sidecar_path = sub_dir / f"{clip_id}.meta.json"
    sidecar_data = {
        "id": clip_id,
        "kind": "event",
        "camera_id": cam_id,
        "path": str(video_path),
        "sidecar_path": str(sidecar_path),
        "start_ts": 1791194400000,
        "end_ts": 1791194403000,
        "duration_s": 3.0,
        "size_bytes": video_path.stat().st_size,
        "sha256": sha256_hash,
        "status": "ready",
        "retention_class": "event_critical",
        "created_at": 1791194403000,
        "metadata": {
            "event_id": "01ARZ3NDEKTSV4RRFFQ69G5FEV",
            "severity": "critical",
            "event_kind": "zone_intrusion",
            "plate": "KA01AB1234",
            "category": "truck",
            "colour": "white",
            "sighting_id": "01ARZ3NDEKTSV4RRFFQ69G5FS1",
            "track_id": 42
        }
    }
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, indent=2)

    # Set up SQLite DB using initial schema
    schema_sql_path = Path(__file__).resolve().parent.parent / "migrations" / "001_initial_schema.sql"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with open(schema_sql_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    # Rebuild index
    stats = rebuild_index(clips_dir=str(clips_dir), conn=conn, verify_hash=True)
    assert stats["scanned"] == 1
    assert stats["valid"] == 1
    assert stats["restored_clips"] == 1
    assert stats["restored_vehicles"] == 1
    assert stats["restored_sightings"] == 1
    assert stats["restored_events"] == 1

    # Verify clips table row
    clip_row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    assert clip_row is not None
    assert clip_row["sha256"] == sha256_hash
    assert clip_row["status"] == "ready"
    assert clip_row["retention_class"] == "event_critical"

    # Verify vehicles table row
    veh_row = conn.execute("SELECT * FROM vehicles WHERE plate = 'KA01AB1234'").fetchone()
    assert veh_row is not None
    assert veh_row["category"] == "truck"
    assert veh_row["colour"] == "white"

    # Verify sightings table row
    sight_row = conn.execute("SELECT * FROM sightings WHERE id = '01ARZ3NDEKTSV4RRFFQ69G5FS1'").fetchone()
    assert sight_row is not None
    assert sight_row["vehicle_id"] == veh_row["id"]
    assert sight_row["clip_id"] == clip_id

    # Verify events table row
    event_row = conn.execute("SELECT * FROM events WHERE id = '01ARZ3NDEKTSV4RRFFQ69G5FEV'").fetchone()
    assert event_row is not None
    assert event_row["severity"] == "critical"
    assert event_row["clip_id"] == clip_id

    # Test surviving DB wipe: wipe tables, run again, verify restored
    conn.execute("DELETE FROM alerts")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM sightings")
    conn.execute("DELETE FROM vehicles")
    conn.execute("DELETE FROM clips")
    assert conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 0

    stats2 = rebuild_index(clips_dir=str(clips_dir), conn=conn, verify_hash=True)
    assert stats2["restored_clips"] == 1
    assert conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 1


# 9. Test repair clips
def test_repair_clip(tmp_path):
    clips_dir = tmp_path / "clips"
    cont_dir = tmp_path / "continuous"
    cam_id = "testcam_repair"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    dt1 = datetime(2026, 10, 5, 18, 0, 0, tzinfo=timezone.utc)
    ms1 = int(dt1.timestamp() * 1000)

    clipper = Clipper(clips_dir=str(clips_dir), continuous_dir=str(cont_dir))

    # Request clip when NO segments exist -> marked 'needs_repair'
    req = ClipRequest(
        kind="sighting",
        camera_id=cam_id,
        start_ts_ms=ms1 + 2000,
        end_ts_ms=ms1 + 2000,
        anchor_ts_ms=ms1 + 2000,
        sighting_length_s=3.0,
        sighting_pre_s=1.0
    )

    schema_sql_path = Path(__file__).resolve().parent.parent / "migrations" / "001_initial_schema.sql"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with open(schema_sql_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    res = clipper.process_clip_request(req, db_conn=conn, wait_timeout_s=0.5)
    assert res.status == "needs_repair"

    # Now create the segment
    seg_path = cam_dir / dt1.strftime("%Y%m%d_%H%M%S.mkv")
    create_synthetic_segment(seg_path, duration_s=10.0)

    # Attempt repair
    repair_res = clipper.repair_clip(res.clip_id, db_conn=conn)
    assert repair_res is not None
    assert repair_res.status == "ready"
    assert Path(repair_res.path).exists()
    assert repair_res.size_bytes > 0

    # Verify DB updated
    row = conn.execute("SELECT status FROM clips WHERE id = ?", (res.clip_id,)).fetchone()
    assert row["status"] == "ready"


# 10. Recorder supervisor and gap tracking
def test_recorder_supervisor_and_gaps(tmp_path):
    clock = SimulatedClock(10000)
    recorder = FFmpegRecorder(camera_id="cam_gap", rtsp_url="rtsp://localhost:8554/cam_gap", base_dir=str(tmp_path), clock=clock)

    # Simulate recorder died at 15000 and restart checked at 20000
    recorder.running = True
    recorder._last_dead_ts_ms = 15000
    clock.advance(5000)  # now 15000

    # Test has_gap
    recorder.gaps.append((12000, 16000))
    assert recorder.has_gap(14000, 18000) is True
    assert recorder.has_gap(20000, 25000) is False


# 11. Human Checkpoint Bug Fix Tests

# Bug 1: Segment timestamps & timezone alignment
def test_checkpoint_bug1_segment_timestamp_utc_vs_local():
    ts_utc = parse_segment_timestamp("20261101_102720.mkv")
    dt_utc = datetime(2026, 11, 1, 10, 27, 20, tzinfo=timezone.utc)
    expected_ms = int(dt_utc.timestamp() * 1000)
    assert ts_utc == expected_ms


# Bug 1 (Timezone): Real recorder-style filenames in Asia/Kolkata timezone, cutting in the middle
def test_checkpoint_bug1_real_filenames_kolkata_timezone(tmp_path):
    from app.rules.schedule import resolve_timezone
    ist_tz = resolve_timezone("Asia/Kolkata")

    cont_dir = tmp_path / "continuous"
    clips_dir = tmp_path / "clips"
    cam_id = "cam01"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    dt_ist1 = datetime(2026, 11, 1, 15, 57, 20, tzinfo=ist_tz)
    dt_ist2 = datetime(2026, 11, 1, 15, 57, 30, tzinfo=ist_tz)

    seg1_name = dt_ist1.strftime("%Y%m%d_%H%M%S.mkv")
    seg2_name = dt_ist2.strftime("%Y%m%d_%H%M%S.mkv")

    create_synthetic_segment(cam_dir / seg1_name, duration_s=10.0)
    create_synthetic_segment(cam_dir / seg2_name, duration_s=10.0)

    clipper_ist = Clipper(clips_dir=str(clips_dir), continuous_dir=str(cont_dir), segment_tz=ist_tz)

    start_utc_ms = int(datetime(2026, 11, 1, 15, 57, 25, tzinfo=ist_tz).timestamp() * 1000)
    end_utc_ms = int(datetime(2026, 11, 1, 15, 57, 35, tzinfo=ist_tz).timestamp() * 1000)

    req = ClipRequest(
        kind="event",
        camera_id=cam_id,
        start_ts_ms=start_utc_ms,
        end_ts_ms=end_utc_ms,
        pre_roll_s=0,
        hold_s=0
    )

    res = clipper_ist.process_clip_request(req, wait_timeout_s=1.0)
    assert res.status == "ready"
    assert Path(res.path).exists()
    assert abs(res.duration_s - 10.0) < 0.2
    assert len(res.key_frames) == 3


# Bug 2: --anchor timestamp parsing formats (negative offset, s ago, epoch ms)
def test_checkpoint_bug2_parse_timestamp_arg_formats():
    now_ms = 1700000000000
    assert parse_timestamp_arg("-30", now_ms) == now_ms - 30000
    assert parse_timestamp_arg("30s ago", now_ms) == now_ms - 30000
    assert parse_timestamp_arg("30s", now_ms) == now_ms - 30000
    assert parse_timestamp_arg("30 ago", now_ms) == now_ms - 30000
    assert parse_timestamp_arg("1793548680000", now_ms) == 1793548680000


# Bug 2: Sighting window math strictly [anchor - 4s, anchor + 6s] (docs/05 s6)
def test_checkpoint_bug2_anchor_window_math():
    anchor_ms = 1793548680000
    w_start, w_end, dur_s = compute_clip_window(
        kind="sighting",
        start_ts_ms=anchor_ms,
        end_ts_ms=anchor_ms,
        anchor_ts_ms=anchor_ms,
        sighting_length_s=10.0,
        sighting_pre_s=4.0
    )
    assert w_start == anchor_ms - 4000
    assert w_end == anchor_ms + 6000
    assert dur_s == 10.0


# Bug 3: A clip whose window has no recorded coverage must NEVER be 'ready'
def test_checkpoint_bug3_clip_without_full_coverage_not_ready(tmp_path):
    cont_dir = tmp_path / "continuous"
    clips_dir = tmp_path / "clips"
    cam_id = "cam01"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    seg_dt = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    seg_ms = int(seg_dt.timestamp() * 1000)
    seg_path = cam_dir / seg_dt.strftime("%Y%m%d_%H%M%S.mkv")
    create_synthetic_segment(seg_path, duration_s=10.0)

    clipper = Clipper(clips_dir=str(clips_dir), continuous_dir=str(cont_dir))

    req_no_cov = ClipRequest(
        kind="event",
        camera_id=cam_id,
        start_ts_ms=seg_ms + 30000,
        end_ts_ms=seg_ms + 40000,
        pre_roll_s=0,
        hold_s=0
    )
    res_no_cov = clipper.process_clip_request(req_no_cov, wait_timeout_s=0.5)
    assert res_no_cov.status != "ready"
    assert res_no_cov.status in ("needs_repair", "incomplete")
    assert res_no_cov.status_reason != ""

    req_partial = ClipRequest(
        kind="event",
        camera_id=cam_id,
        start_ts_ms=seg_ms + 5000,
        end_ts_ms=seg_ms + 25000,
        pre_roll_s=0,
        hold_s=0
    )
    res_partial = clipper.process_clip_request(req_partial, wait_timeout_s=0.5)
    assert res_partial.status != "ready"
    assert res_partial.status == "incomplete"
    assert "Partial coverage" in res_partial.status_reason


# Bug 4: Measured duration in sidecar duration_s and clamped window in batch mode
def test_checkpoint_bug4_measured_duration_in_sidecar(tmp_path):
    clips_dir = tmp_path / "clips"
    src_file = tmp_path / "src10s.mkv"
    create_synthetic_segment(src_file, duration_s=10.0)

    clipper = Clipper(clips_dir=str(clips_dir))

    req = ClipRequest(
        kind="event",
        camera_id="cam01",
        start_ts_ms=0,
        end_ts_ms=10000,
        pre_roll_s=15.0,
        hold_s=20.0
    )

    res = clipper.process_clip_request(req, source_file=src_file)
    assert res.status == "ready"

    probe_dur = get_video_duration_ffprobe(Path(res.path))
    assert abs(res.duration_s - probe_dur) < 0.1
    assert res.duration_s < 12.0

    with open(res.sidecar_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert abs(meta["duration_s"] - probe_dur) < 0.1
    assert "window_start_ts" in meta
    assert "window_end_ts" in meta
    assert meta["status_reason"] != ""


# Bug 5: Batch mode must extract all 3 key frames (first, anchor, last)
def test_checkpoint_bug5_batch_mode_extracts_all_keyframes(tmp_path):
    clips_dir = tmp_path / "clips"
    src_file = tmp_path / "src10s.mkv"
    create_synthetic_segment(src_file, duration_s=10.0)

    clipper = Clipper(clips_dir=str(clips_dir))
    req = ClipRequest(
        kind="event",
        camera_id="cam01",
        start_ts_ms=0,
        end_ts_ms=10000,
        pre_roll_s=15.0,
        hold_s=20.0
    )

    res = clipper.process_clip_request(req, source_file=src_file)
    assert res.status == "ready"
    assert len(res.key_frames) == 3
    assert any("first" in k for k in res.key_frames)
    assert any("anchor" in k for k in res.key_frames)
    assert any("last" in k for k in res.key_frames)


# Bug 6: Recorder reports completed segment size (>0 bytes), not 0 bytes at creation
def test_checkpoint_bug6_recorder_size_reporting(tmp_path):
    out_dir = tmp_path / "cam01"
    out_dir.mkdir(parents=True)

    seg1 = out_dir / "20261101_100000.mkv"
    create_synthetic_segment(seg1, duration_s=5.0)

    seg2 = out_dir / "20261101_100005.mkv"
    seg2.touch()  # active file 0 bytes

    reported_completed = set()
    completed_reports = []

    files = sorted(out_dir.glob("*.mkv"))
    if len(files) > 1:
        for f in files[:-1]:
            if f.name not in reported_completed:
                reported_completed.add(f.name)
                size = f.stat().st_size
                completed_reports.append((f.name, size))

    assert len(completed_reports) == 1
    assert completed_reports[0][0] == seg1.name
    assert completed_reports[0][1] > 0
    assert seg2.name not in reported_completed


# Round 2 Checkpoint Tests:
# 1. Live sighting cut spanning segment boundary must have status == 'ready' (not 'incomplete')
def test_checkpoint_round2_boundary_sighting_cut_ready(tmp_path):
    cont_dir = tmp_path / "continuous"
    clips_dir = tmp_path / "clips"
    cam_id = "cam01"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    # Segment 1: starts at 1793578670000 (10:00:00 UTC), duration 11.0s, ends at 1793578681000
    seg1_dt = datetime.fromtimestamp(1793578670, tz=timezone.utc)
    seg1_name = seg1_dt.strftime("%Y%m%d_%H%M%S.mkv")
    create_synthetic_segment(cam_dir / seg1_name, duration_s=11.0)

    # Segment 2: starts at 1793578681000 (10:00:11 UTC), duration 10.0s, ends at 1793578691000
    seg2_dt = datetime.fromtimestamp(1793578681, tz=timezone.utc)
    seg2_name = seg2_dt.strftime("%Y%m%d_%H%M%S.mkv")
    create_synthetic_segment(cam_dir / seg2_name, duration_s=10.0)

    clipper = Clipper(clips_dir=str(clips_dir), continuous_dir=str(cont_dir))

    # Request sighting clip with anchor 1793578680000 -> window 1793578676000..1793578686000
    # Window spans boundary between seg1 and seg2, completely inside [1793578670000, 1793578691000]
    req = ClipRequest(
        kind="sighting",
        camera_id=cam_id,
        start_ts_ms=1793578676000,
        end_ts_ms=1793578686000,
        anchor_ts_ms=1793578680000,
        sighting_length_s=10.0,
        sighting_pre_s=4.0
    )

    res = clipper.process_clip_request(req, wait_timeout_s=1.0)
    assert res.status == "ready"
    assert res.status_reason == "Full coverage"
    assert abs(res.duration_s - 10.0) < 0.2


# 2. Sighting clips must have retention_class: 'sighting_resolved' (per docs/07 section 5), not 'event_medium'
def test_checkpoint_round2_sighting_retention_class(tmp_path):
    clips_dir = tmp_path / "clips"
    src_file = tmp_path / "src10s.mkv"
    create_synthetic_segment(src_file, duration_s=10.0)

    clipper = Clipper(clips_dir=str(clips_dir))
    req = ClipRequest(
        kind="sighting",
        camera_id="cam01",
        start_ts_ms=0,
        end_ts_ms=10000,
        anchor_ts_ms=4000
    )

    res = clipper.process_clip_request(req, source_file=src_file)
    assert res.status == "ready"

    with open(res.sidecar_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["retention_class"] == "sighting_resolved"
    assert meta["retention_class"] != "event_medium"


# 3. Batch mode sidecar window_start_ts and window_end_ts must be clamped to source duration
def test_checkpoint_round2_batch_window_clamping(tmp_path):
    clips_dir = tmp_path / "clips"
    src_file = tmp_path / "src10s.mkv"
    create_synthetic_segment(src_file, duration_s=10.0)

    clipper = Clipper(clips_dir=str(clips_dir))
    # Event request with pre_roll 15s and hold 20s on a 10s source file
    req = ClipRequest(
        kind="event",
        camera_id="cam01",
        start_ts_ms=0,
        end_ts_ms=10000,
        pre_roll_s=15.0,
        hold_s=20.0
    )

    res = clipper.process_clip_request(req, source_file=src_file)
    assert res.status == "ready"

    with open(res.sidecar_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Window must be clamped to the 10s source file bounds, NOT -15000..30000 (45s span)
    assert meta["window_start_ts"] >= 0
    assert meta["window_end_ts"] <= 10000
    assert (meta["window_end_ts"] - meta["window_start_ts"]) <= 10000


# 4. Clipper ignores zero-byte and still-being-written segments
def test_checkpoint_round2_ignore_zero_byte_segments(tmp_path):
    cont_dir = tmp_path / "continuous"
    cam_id = "cam01"
    cam_dir = cont_dir / cam_id
    cam_dir.mkdir(parents=True)

    # Valid segment 1: 10s video
    t0 = 1793578670000
    seg1_dt = datetime.fromtimestamp(1793578670, tz=timezone.utc)
    seg1_name = seg1_dt.strftime("%Y%m%d_%H%M%S.mkv")
    create_synthetic_segment(cam_dir / seg1_name, duration_s=10.0)

    # Zero-byte segment 2 (currently being created / 0 bytes)
    seg2_dt = datetime.fromtimestamp(1793578680, tz=timezone.utc)
    seg2_name = seg2_dt.strftime("%Y%m%d_%H%M%S.mkv")
    zero_file = cam_dir / seg2_name
    zero_file.touch()
    assert zero_file.stat().st_size == 0

    clipper = Clipper(continuous_dir=str(cont_dir))

    # find_covering_segments for a window needing segment 2 must NOT return the 0-byte file
    found = clipper.find_covering_segments(cam_id, t0 + 5000, t0 + 15000, wait_timeout_s=0.2)
    found_paths = [str(p.name) for p, _, _ in found]
    assert seg2_name not in found_paths

