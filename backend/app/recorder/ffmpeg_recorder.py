"""FFmpeg continuous segmented recorder and supervisor.

docs/07 s2:
One FFmpeg per camera:
-rtsp_transport tcp -i <url> -an -c copy -f segment -segment_time 10
-segment_format matroska -strftime 1 -reset_timestamps 1 ...
No re-encode, no audio, MKV so crash doesn't corrupt.
Supervisor restarts a dead recorder within 5s and logs recording_gap.
"""

import os
import subprocess
import threading
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from app.core.clock import Clock

logger = logging.getLogger(__name__)


class FFmpegRecorder:
    """Supervised single-camera continuous segmented recorder."""

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        base_dir: str = "data/continuous",
        clock: Optional[Clock] = None,
        segment_time_s: int = 10
    ):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.base_dir = Path(base_dir) / camera_id
        self.clock = clock or Clock()
        self.segment_time_s = segment_time_s

        self.process: Optional[subprocess.Popen] = None
        self.running = False
        self.gaps: List[Tuple[int, int]] = []  # list of (gap_start_ms, gap_end_ms)
        self._last_dead_ts_ms: Optional[int] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the continuous FFmpeg recording process."""
        with self._lock:
            if self.running and self.is_alive():
                return

            self.base_dir.mkdir(parents=True, exist_ok=True)
            output_pattern = str(self.base_dir / "%Y%m%d_%H%M%S.mkv")

            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "warning",
                "-rtsp_transport", "tcp",
                "-i", self.rtsp_url,
                "-an",
                "-c", "copy",
                "-f", "segment",
                "-segment_time", str(self.segment_time_s),
                "-segment_format", "matroska",
                "-strftime", "1",
                "-reset_timestamps", "1",
                output_pattern
            ]

            now_ms = self.clock.now_ms()
            if self._last_dead_ts_ms is not None:
                # Log recording gap from when it died until now
                gap_start = self._last_dead_ts_ms
                gap_end = now_ms
                self.gaps.append((gap_start, gap_end))
                logger.warning(
                    f"Recording gap on {self.camera_id}: "
                    f"{(gap_end - gap_start) / 1000.0:.1f}s ({gap_start} -> {gap_end})"
                )
                self._last_dead_ts_ms = None

            env = os.environ.copy()
            env["TZ"] = "UTC"
            try:
                # Start background subprocess with UTC timezone for cross-platform strftime
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    env=env
                )
                self.running = True
                logger.info(f"Started continuous recording for camera {self.camera_id} at {self.base_dir}")
            except Exception as e:
                logger.error(f"Failed to start FFmpeg for {self.camera_id}: {e}")
                self._last_dead_ts_ms = now_ms
                self.running = False

    def is_alive(self) -> bool:
        """Check if FFmpeg subprocess is still running."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def check_health(self) -> bool:
        """Supervise recorder: restart if died unexpectedly."""
        with self._lock:
            if not self.running:
                return False

            if not self.is_alive():
                now_ms = self.clock.now_ms()
                if self._last_dead_ts_ms is None:
                    self._last_dead_ts_ms = now_ms
                    logger.warning(f"FFmpeg recorder died for {self.camera_id}")

                # Restart immediately
                self.start()
                return False
            return True

    def stop(self) -> None:
        """Stop the continuous recording gracefully."""
        with self._lock:
            self.running = False
            if self.process and self.is_alive():
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3.0)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            self.process = None
            logger.info(f"Stopped continuous recording for camera {self.camera_id}")

    def has_gap(self, start_ms: int, end_ms: int) -> bool:
        """Check if a time window overlaps any known recording gap."""
        for g_start, g_end in self.gaps:
            if not (end_ms < g_start or start_ms > g_end):
                return True
        return False


class RecorderSupervisor:
    """Supervises multiple camera continuous recorders."""

    def __init__(
        self,
        base_dir: str = "data/continuous",
        clock: Optional[Clock] = None,
        check_interval_s: float = 2.0
    ):
        self.base_dir = base_dir
        self.clock = clock or Clock()
        self.check_interval_s = check_interval_s
        self.recorders: Dict[str, FFmpegRecorder] = {}
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    def start_camera(self, camera_id: str, rtsp_url: str) -> FFmpegRecorder:
        """Register and start recording a camera."""
        with self._lock:
            if camera_id in self.recorders:
                rec = self.recorders[camera_id]
                if rec.is_alive():
                    return rec
                rec.stop()

            rec = FFmpegRecorder(
                camera_id=camera_id,
                rtsp_url=rtsp_url,
                base_dir=self.base_dir,
                clock=self.clock
            )
            rec.start()
            self.recorders[camera_id] = rec

            if not self._running:
                self.start_supervisor()

            return rec

    def stop_camera(self, camera_id: str) -> None:
        """Stop recording a single camera."""
        with self._lock:
            rec = self.recorders.pop(camera_id, None)
            if rec:
                rec.stop()

    def get_recorder(self, camera_id: str) -> Optional[FFmpegRecorder]:
        """Get the recorder instance for a camera."""
        with self._lock:
            return self.recorders.get(camera_id)

    def start_supervisor(self) -> None:
        """Start the background watchdog thread."""
        self._running = True
        self._thread = threading.Thread(target=self._supervise_loop, daemon=True)
        self._thread.start()

    def stop_all(self) -> None:
        """Stop all camera recorders and supervisor."""
        self._running = False
        with self._lock:
            for rec in self.recorders.values():
                rec.stop()
            self.recorders.clear()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _supervise_loop(self) -> None:
        while self._running:
            with self._lock:
                for rec in list(self.recorders.values()):
                    rec.check_health()
            time.sleep(self.check_interval_s)


def main():
    import argparse
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


