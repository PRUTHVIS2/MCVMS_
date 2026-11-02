"""CLI tool to run continuous supervised recording for a camera.

docs/07 s2 & PLAN.md Step 5:
Continuous MKV segmented recording with supervision and gap detection.
"""

import time
import argparse
import logging
from pathlib import Path

from app.recorder.ffmpeg_recorder import FFmpegRecorder


def main():
    parser = argparse.ArgumentParser(description="Run continuous recorder for a camera")
    parser.add_argument("--camera", default="cam01", help="Camera ID (default: cam01)")
    parser.add_argument("--url", default="rtsp://localhost:8554/cam01", help="RTSP URL or video file (default: rtsp://localhost:8554/cam01)")
    parser.add_argument("--base-dir", default="data/continuous", help="Base directory for continuous segments (default: data/continuous)")
    parser.add_argument("--segment-time", type=int, default=10, help="Segment length in seconds (default: 10)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    out_dir = Path(args.base_dir) / args.camera
    print(f"\n============================================================")
    print(f"Starting Continuous Recorder for '{args.camera}'")
    print(f"  Source:       {args.url}")
    print(f"  Destination:  {out_dir}")
    print(f"  Segment Time: {args.segment_time}s")
    print(f"Press Ctrl+C to stop.")
    print(f"============================================================\n")

    recorder = FFmpegRecorder(
        camera_id=args.camera,
        rtsp_url=args.url,
        base_dir=args.base_dir,
        segment_time_s=args.segment_time
    )

    recorder.start()
    reported_completed = set()

    try:
        while True:
            time.sleep(2.0)
            recorder.check_health()
            if out_dir.exists():
                files = sorted(out_dir.glob("*.mkv"))
                # Any segment before the latest active file is closed and completed
                if len(files) > 1:
                    for f in files[:-1]:
                        if f.name not in reported_completed:
                            reported_completed.add(f.name)
                            size = f.stat().st_size
                            print(f"  [Segment completed] {f.name} ({size / (1024*1024):.2f} MB / {size} bytes)")
    except KeyboardInterrupt:
        print("\nStopping recorder...")
    finally:
        recorder.stop()
        if out_dir.exists():
            for f in sorted(out_dir.glob("*.mkv")):
                if f.name not in reported_completed:
                    reported_completed.add(f.name)
                    size = f.stat().st_size
                    print(f"  [Segment completed] {f.name} ({size / (1024*1024):.2f} MB / {size} bytes)")
        print("Recorder stopped cleanly.\n")


if __name__ == "__main__":
    main()

