"""Index rebuild tool.

docs/07 s4 & PLAN.md Step 5:
Walk data/clips/**/*.meta.json, verify file hash, rebuild SQLite records.
Survives DB wipe. Restores clips, events, sightings, and vehicles.
"""

import os
import sys
import json
import hashlib
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import sqlite3

from app.core.clock import Clock
from app.core.db import get_connection
from app.recorder.clipper import compute_sha256

logger = logging.getLogger(__name__)


def verify_clip_file(meta_data: Dict[str, Any], meta_file_path: Path, verify_hash: bool = True) -> Tuple[bool, str, str]:
    """Verify video file exists and SHA-256 matches.
    
    Returns (is_valid, resolved_video_path, error_reason).
    """
    raw_path = meta_data.get("path")
    resolved_path: Optional[Path] = None

    if raw_path:
        p = Path(raw_path)
        if p.exists():
            resolved_path = p

    # If raw path does not exist (e.g. moved directory), check sibling .mp4
    if resolved_path is None or not resolved_path.exists():
        clip_id = meta_data.get("id")
        candidate = meta_file_path.with_name(f"{clip_id}.mp4") if clip_id else meta_file_path.with_suffix(".mp4")
        if candidate.exists():
            resolved_path = candidate

    if resolved_path is None or not resolved_path.exists():
        return False, "", "Video file missing on disk"

    if verify_hash:
        expected_hash = meta_data.get("sha256")
        if expected_hash:
            actual_hash = compute_sha256(resolved_path)
            if actual_hash != expected_hash:
                return False, str(resolved_path), f"SHA-256 mismatch: expected {expected_hash}, got {actual_hash}"

    return True, str(resolved_path), ""


def rebuild_index(
    clips_dir: str = "data/clips",
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    verify_hash: bool = True,
    dry_run: bool = False,
    clock: Optional[Clock] = None
) -> Dict[str, int]:
    """Walk clips_dir, verify sidecars and video hashes, and restore SQLite records."""
    clock = clock or Clock()
    close_conn = False

    if conn is None:
        if db_path is not None:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            close_conn = True
        else:
            conn = get_connection()

    clips_path = Path(clips_dir)
    stats = {
        "scanned": 0,
        "valid": 0,
        "restored_clips": 0,
        "restored_vehicles": 0,
        "restored_sightings": 0,
        "restored_events": 0,
        "mismatches": 0,
        "missing_video": 0,
    }

    if not clips_path.exists():
        logger.warning(f"Clips directory does not exist: {clips_path}")
        return stats

    meta_files = list(clips_path.glob("**/*.meta.json"))
    stats["scanned"] = len(meta_files)

    for meta_file in meta_files:
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read sidecar {meta_file}: {e}")
            continue

        clip_id = meta.get("id")
        kind = meta.get("kind", "event")
        camera_id = meta.get("camera_id", "unknown")
        start_ts = meta.get("start_ts")
        end_ts = meta.get("end_ts")
        duration_s = meta.get("duration_s", 0.0)
        size_bytes = meta.get("size_bytes", 0)
        expected_sha = meta.get("sha256", "")
        status = meta.get("status", "ready")
        retention_class = meta.get("retention_class", "event_medium")
        created_at = meta.get("created_at", clock.now_ms())
        metadata = meta.get("metadata", {})

        is_valid, video_path, err = verify_clip_file(meta, meta_file, verify_hash=verify_hash)

        if not is_valid:
            if "missing" in err.lower():
                stats["missing_video"] += 1
                status = "needs_repair"
            else:
                stats["mismatches"] += 1
                status = "needs_repair"
            logger.warning(f"Clip {clip_id} verification issue: {err}")
        else:
            stats["valid"] += 1

        if dry_run:
            continue

        # 1. Ensure camera exists in cameras table to satisfy foreign keys
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO cameras (id, name, rtsp_url_enc, created_at)
                VALUES (?, ?, '', ?)
                """,
                (camera_id, camera_id, created_at)
            )
        except Exception as e:
            logger.debug(f"Note on camera insert: {e}")

        # 2. Upsert clips table
        conn.execute(
            """
            INSERT INTO clips (
                id, kind, camera_id, path, sidecar_path, start_ts, end_ts,
                duration_s, size_bytes, sha256, status, retention_class, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                path = excluded.path,
                sidecar_path = excluded.sidecar_path,
                start_ts = excluded.start_ts,
                end_ts = excluded.end_ts,
                duration_s = excluded.duration_s,
                size_bytes = excluded.size_bytes,
                sha256 = excluded.sha256,
                status = excluded.status,
                retention_class = excluded.retention_class
            """,
            (
                clip_id, kind, camera_id, video_path or str(meta.get("path", "")),
                str(meta_file), start_ts, end_ts, duration_s, size_bytes,
                expected_sha, status, retention_class, created_at
            )
        )
        stats["restored_clips"] += 1

        # 3. Check for vehicle in metadata and restore
        vehicle_id = None
        veh_data = metadata.get("vehicle") or metadata.get("vehicle_info")
        plate = None
        if veh_data and isinstance(veh_data, dict):
            plate = veh_data.get("plate")
        elif "plate" in metadata:
            plate = metadata["plate"]

        if plate:
            cur = conn.execute("SELECT id FROM vehicles WHERE plate = ?", (plate,))
            row = cur.fetchone()
            if row:
                vehicle_id = row["id"]
            else:
                category = metadata.get("category") or (veh_data.get("category") if isinstance(veh_data, dict) else None)
                colour = metadata.get("colour") or (veh_data.get("colour") if isinstance(veh_data, dict) else None)
                cur = conn.execute(
                    """
                    INSERT INTO vehicles (plate, plate_source, category, colour, first_seen, last_seen, sightings_count)
                    VALUES (?, 'auto', ?, ?, ?, ?, 1)
                    """,
                    (plate, category, colour, start_ts or created_at, end_ts or created_at)
                )
                vehicle_id = cur.lastrowid
                stats["restored_vehicles"] += 1

        # 4. Check for sighting in metadata
        sighting_id = metadata.get("sighting_id")
        if sighting_id:
            track_id = metadata.get("track_id", 1)
            source = metadata.get("source", "batch")
            category = metadata.get("category")
            colour = metadata.get("colour")
            sighting_status = metadata.get("sighting_status", "resolved")

            conn.execute(
                """
                INSERT OR IGNORE INTO sightings (
                    id, camera_id, track_id, source, first_ts, last_ts,
                    category, colour, plate_final, status, vehicle_id, clip_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sighting_id, camera_id, track_id, source,
                    start_ts or created_at, end_ts or created_at,
                    category, colour, plate, sighting_status, vehicle_id, clip_id, created_at
                )
            )
            stats["restored_sightings"] += 1

        # 5. Check for event in metadata
        event_id = metadata.get("event_id")
        if event_id:
            action_id = metadata.get("action_id")
            zone_id = metadata.get("zone_id")
            severity = metadata.get("severity", "medium")
            event_kind = metadata.get("event_kind", kind)
            track_id = metadata.get("track_id")
            subject_json = json.dumps(metadata.get("subject", {}))

            conn.execute(
                """
                INSERT OR IGNORE INTO events (
                    id, action_id, zone_id, camera_id, severity, kind,
                    status, started_at, ended_at, track_id, subject_json,
                    vehicle_id, sighting_id, clip_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, action_id, zone_id, camera_id, severity, event_kind,
                    start_ts or created_at, end_ts or created_at, track_id, subject_json,
                    vehicle_id, sighting_id, clip_id
                )
            )
            stats["restored_events"] += 1

    if not dry_run:
        conn.commit()

    if close_conn:
        conn.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Rebuild SQLite records from clip sidecars")
    parser.add_argument("--clips-dir", default="data/clips", help="Directory containing clip sidecars")
    parser.add_argument("--db", default=None, help="SQLite database path")
    parser.add_argument("--skip-hash", action="store_true", help="Skip SHA-256 integrity verification")
    parser.add_argument("--dry-run", action="store_true", help="Scan and verify without modifying database")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print(f"Rebuilding index from {args.clips_dir}...")
    stats = rebuild_index(
        clips_dir=args.clips_dir,
        db_path=args.db,
        verify_hash=not args.skip_hash,
        dry_run=args.dry_run
    )

    print("\nRebuild Index Summary:")
    print(f"  Scanned Sidecars:   {stats['scanned']}")
    print(f"  Valid Clips:        {stats['valid']}")
    print(f"  Restored Clips:     {stats['restored_clips']}")
    print(f"  Restored Vehicles:  {stats['restored_vehicles']}")
    print(f"  Restored Sightings: {stats['restored_sightings']}")
    print(f"  Restored Events:    {stats['restored_events']}")
    print(f"  Hash Mismatches:    {stats['mismatches']}")
    print(f"  Missing Videos:     {stats['missing_video']}")


if __name__ == "__main__":
    main()

