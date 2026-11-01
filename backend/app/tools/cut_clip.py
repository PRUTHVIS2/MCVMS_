"""CLI tool for cutting clips.

docs/07 s3 & PLAN.md Step 5:
Request an event clip or sighting clip from recorded continuous segments or directly from a file.
Outputs the resulting MP4 path, duration, SHA-256, and sidecar path.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from app.core.clock import Clock
from app.recorder.clipper import Clipper, ClipRequest

logger = logging.getLogger(__name__)


def parse_timestamp_arg(val: Optional[str], now_ms: int) -> Optional[int]:
    """Parse integer ms, negative offset (e.g. -30 for 30s ago), or ISO 8601."""
    if val is None:
        return None
    val = val.strip()
    try:
        # Check if direct integer milliseconds
        num = int(val)
        if -86400 <= num <= 0:
            # Negative or small offset in seconds
            return now_ms + (num * 1000)
        return num
    except ValueError:
        pass

    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception as e:
        raise ValueError(f"Could not parse timestamp '{val}': {e}")


def main():
    parser = argparse.ArgumentParser(description="Cut event or sighting clips from continuous recording or source file")
    parser.add_argument("--camera", default="cam01", help="Camera ID (default: cam01)")
    parser.add_argument("--kind", choices=["event", "sighting"], default="event", help="Clip kind")
    parser.add_argument("--start", help="Start timestamp (epoch ms, ISO8601, or seconds ago e.g. -30)")
    parser.add_argument("--end", help="End timestamp (epoch ms, ISO8601, or seconds ago)")
    parser.add_argument("--duration", type=float, help="Clip duration in seconds (if start/end not fully specified)")
    parser.add_argument("--anchor", help="Anchor timestamp for sighting clips (epoch ms or seconds ago)")
    parser.add_argument("--source-file", help="Path to video file for batch mode cutting")
    parser.add_argument("--continuous-dir", default="data/continuous", help="Continuous recordings base directory")
    parser.add_argument("--clips-dir", default="data/clips", help="Clips output base directory")
    parser.add_argument("--pre-roll", type=float, default=15.0, help="Pre-roll in seconds (default: 15.0)")
    parser.add_argument("--hold", type=float, default=20.0, help="Hold in seconds (default: 20.0)")
    parser.add_argument("--wait", type=float, default=15.0, help="Segment wait timeout in seconds (default: 15.0)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    clock = Clock()
    now_ms = clock.now_ms()

    # Determine start and end timestamps
    start_ms = parse_timestamp_arg(args.start, now_ms)
    end_ms = parse_timestamp_arg(args.end, now_ms)
    anchor_ms = parse_timestamp_arg(args.anchor, now_ms)

    if start_ms is None and end_ms is None:
        duration_s = args.duration or (10.0 if args.kind == "sighting" else 25.0)
        # Default: recent window
        end_ms = now_ms
        start_ms = now_ms - int(duration_s * 1000)
    elif start_ms is not None and end_ms is None:
        duration_s = args.duration or 10.0
        end_ms = start_ms + int(duration_s * 1000)
    elif start_ms is None and end_ms is not None:
        duration_s = args.duration or 10.0
        start_ms = end_ms - int(duration_s * 1000)

    if args.kind == "sighting" and anchor_ms is None:
        anchor_ms = start_ms + int(((end_ms - start_ms) / 2))

    clipper = Clipper(
        clips_dir=args.clips_dir,
        continuous_dir=args.continuous_dir,
        clock=clock
    )

    req = ClipRequest(
        kind=args.kind,
        camera_id=args.camera,
        start_ts_ms=start_ms,
        end_ts_ms=end_ms,
        anchor_ts_ms=anchor_ms,
        pre_roll_s=args.pre_roll,
        hold_s=args.hold
    )

    source_path = Path(args.source_file) if args.source_file else None

    print(f"\nCutting {args.kind} clip for camera '{args.camera}'...")
    print(f"  Window: {start_ms} -> {end_ms} (duration: {(end_ms - start_ms) / 1000.0:.1f}s)")
    if source_path:
        print(f"  Source file: {source_path}")

    res = clipper.process_clip_request(req, source_file=source_path)

    print("\n" + "=" * 60)
    print("Clip Cutting Result:")
    print(f"  Clip ID:     {res.clip_id}")
    print(f"  Status:      {res.status}")
    print(f"  MP4 Path:    {res.path}")
    print(f"  Sidecar:     {res.sidecar_path}")
    print(f"  Duration:    {res.duration_s:.2f}s")
    print(f"  Size:        {res.size_bytes} bytes")
    print(f"  SHA-256:     {res.sha256}")
    print(f"  Key frames:  {res.key_frames}")
    print("=" * 60)

    if res.status in ("ready", "incomplete"):
        clean_url = Path(res.path).resolve().as_uri()
        print(f"\nPlayback in browser: {clean_url}\n")
    else:
        print(f"\nWarning: Clip cutting resulted in status '{res.status}'\n")


if __name__ == "__main__":
    main()

