"""Clip cutting service for event and sighting clips.

docs/07 s3 & docs/05 s6:
- Event clip: start - pre_roll_s (15s) to end + hold_s (20s), capped at max_clip_min.
- Sighting clip: exactly 10s anchor window [anchor - 4s, anchor + 6s].
- Method: segment lookup, wait up to 15s for covering segments, concat, trim,
  re-encode (h264_nvenc with libx264 fallback), atomic write, SHA-256, sidecar, key frames.
- Batch mode: cuts directly from source video file.
"""

import os
import json
import hashlib
import subprocess
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import ulid

from app.core.clock import Clock

logger = logging.getLogger(__name__)


@dataclass
class ClipRequest:
    """Request to generate a clip."""
    kind: str  # 'event' | 'sighting'
    camera_id: str
    start_ts_ms: int
    end_ts_ms: int
    anchor_ts_ms: Optional[int] = None
    pre_roll_s: float = 15.0
    hold_s: float = 20.0
    max_clip_min: float = 15.0
    sighting_length_s: float = 10.0
    sighting_pre_s: float = 4.0
    retention_class: str = "event_medium"
    metadata: Dict[str, Any] = field(default_factory=dict)
    clip_id: Optional[str] = None


@dataclass
class ClipResult:
    """Outcome of clip cutting."""
    clip_id: str
    kind: str
    camera_id: str
    path: str
    sidecar_path: str
    start_ts: int
    end_ts: int
    duration_s: float
    size_bytes: int
    sha256: str
    status: str  # 'ready' | 'incomplete' | 'needs_repair' | 'failed'
    key_frames: List[str]
    created_at: int


def compute_clip_window(
    kind: str,
    start_ts_ms: int,
    end_ts_ms: int,
    pre_roll_s: float = 15.0,
    hold_s: float = 20.0,
    max_clip_min: float = 15.0,
    anchor_ts_ms: Optional[int] = None,
    sighting_length_s: float = 10.0,
    sighting_pre_s: float = 4.0
) -> Tuple[int, int, float]:
    """Calculate exact [window_start_ms, window_end_ms] and duration_s.
    
    docs/07 s3:
    Event: start - pre_roll_s to end + hold_s, capped at max_clip_min.
    Sighting: exactly 10s anchored around anchor_ts_ms [anchor - pre_s, anchor + (length_s - pre_s)].
    """
    if kind == "sighting":
        anchor = anchor_ts_ms if anchor_ts_ms is not None else start_ts_ms
        window_start = anchor - int(sighting_pre_s * 1000)
        window_end = window_start + int(sighting_length_s * 1000)
        duration_s = sighting_length_s
        return window_start, window_end, duration_s

    # Default: kind == "event"
    window_start = start_ts_ms - int(pre_roll_s * 1000)
    window_end = end_ts_ms + int(hold_s * 1000)
    max_duration_ms = int(max_clip_min * 60 * 1000)

    if (window_end - window_start) > max_duration_ms:
        window_end = window_start + max_duration_ms

    duration_s = (window_end - window_start) / 1000.0
    return window_start, window_end, duration_s


def parse_segment_timestamp(filename_or_path: str) -> Optional[int]:
    """Parse segment timestamp YYYYMMDD_HHMMSS from filename to epoch ms."""
    name = Path(filename_or_path).stem
    # Example: 20261005_100000
    try:
        dt = datetime.strptime(name, "%Y%m%d_%H%M%S")
        # Interpret in UTC for consistency
        dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_video_duration_ffprobe(filepath: Path) -> float:
    """Get accurate duration of a video file using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(filepath)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


class Clipper:
    """Cuts, encodes, and sidecars event and sighting clips."""

    def __init__(
        self,
        clips_dir: str = "data/clips",
        continuous_dir: str = "data/continuous",
        clock: Optional[Clock] = None
    ):
        self.clips_dir = Path(clips_dir)
        self.continuous_dir = Path(continuous_dir)
        self.clock = clock or Clock()

    def find_covering_segments(
        self,
        camera_id: str,
        window_start_ms: int,
        window_end_ms: int,
        segment_duration_s: float = 10.0,
        wait_timeout_s: float = 15.0
    ) -> List[Tuple[Path, int, int]]:
        """Find continuous segment files covering the window.
        
        Returns list of (segment_path, seg_start_ms, seg_end_ms).
        Waits up to wait_timeout_s for newly written segments to appear.
        """
        cam_dir = self.continuous_dir / camera_id
        deadline = time.time() + wait_timeout_s

        while True:
            if not cam_dir.exists():
                time.sleep(0.5)
                if time.time() > deadline:
                    break
                continue

            available_segments: List[Tuple[Path, int, int]] = []
            files = sorted(cam_dir.glob("*.mkv"))

            for f in files:
                seg_start = parse_segment_timestamp(f.name)
                if seg_start is None:
                    continue
                # Estimated or probe segment end
                seg_end = seg_start + int(segment_duration_s * 1000)
                available_segments.append((f, seg_start, seg_end))

            # Filter overlapping segments
            overlapping = [
                (f, s_start, s_end)
                for f, s_start, s_end in available_segments
                if not (s_end < window_start_ms or s_start > window_end_ms)
            ]

            # Check if latest overlapping segment covers window_end_ms
            if overlapping:
                latest_seg_end = max(s_end for _, _, s_end in overlapping)
                if latest_seg_end >= window_end_ms:
                    return overlapping

            if time.time() >= deadline:
                # Return whatever partial segments we found
                return overlapping

            time.sleep(0.5)

        return []

    def cut_clip_from_file(
        self,
        source_video: Path,
        output_path: Path,
        start_offset_s: float,
        duration_s: float
    ) -> bool:
        """Cut and re-encode a clip directly from a video file (batch mode)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output = output_path.with_name(f"{output_path.name}.tmp.{os.getpid()}.mp4")

        # Try h264_nvenc first, fallback to libx264
        codecs_to_try = [
            ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "24"],
            ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
        ]

        success = False
        for codec_args in codecs_to_try:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", f"{start_offset_s:.3f}",
                "-i", str(source_video),
                "-t", f"{duration_s:.3f}"
            ] + codec_args + [
                "-pix_fmt", "yuv420p",
                "-an",
                "-movflags", "+faststart",
                "-y",
                str(temp_output)
            ]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and temp_output.exists() and temp_output.stat().st_size > 0:
                success = True
                break

        if success:
            os.replace(temp_output, output_path)
            return True
        else:
            if temp_output.exists():
                try:
                    temp_output.unlink()
                except Exception:
                    pass
            return False

    def cut_clip_from_segments(
        self,
        segments: List[Tuple[Path, int, int]],
        output_path: Path,
        window_start_ms: int,
        duration_s: float
    ) -> bool:
        """Concat and trim segments to create exact clip."""
        if not segments:
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output = output_path.with_name(f"{output_path.name}.tmp.{os.getpid()}.mp4")

        # Create concat list file
        concat_txt = output_path.with_name(f"{output_path.stem}.concat.txt")
        first_seg_start = segments[0][1]
        offset_s = max(0.0, (window_start_ms - first_seg_start) / 1000.0)

        with open(concat_txt, "w", encoding="utf-8") as f:
            for p, _, _ in segments:
                # Use forward slashes for ffmpeg concat list
                clean_path = str(p.resolve()).replace("\\", "/")
                f.write(f"file '{clean_path}'\n")

        codecs_to_try = [
            ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "24"],
            ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
        ]

        success = False
        for codec_args in codecs_to_try:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-ss", f"{offset_s:.3f}",
                "-i", str(concat_txt),
                "-t", f"{duration_s:.3f}"
            ] + codec_args + [
                "-pix_fmt", "yuv420p",
                "-an",
                "-movflags", "+faststart",
                "-y",
                str(temp_output)
            ]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and temp_output.exists() and temp_output.stat().st_size > 0:
                success = True
                break

        if concat_txt.exists():
            try:
                concat_txt.unlink()
            except Exception:
                pass

        if success:
            os.replace(temp_output, output_path)
            return True
        else:
            if temp_output.exists():
                try:
                    temp_output.unlink()
                except Exception:
                    pass
            return False

    def extract_key_frames(
        self,
        clip_path: Path,
        duration_s: float
    ) -> List[str]:
        """Extract first, anchor/middle, and last keyframes as JPEGs."""
        if not clip_path.exists() or duration_s <= 0:
            return []

        base_stem = clip_path.stem
        parent = clip_path.parent
        key_frames = []

        timestamps = [
            ("first", 0.0),
            ("anchor", duration_s / 2.0),
            ("last", max(0.0, duration_s - 0.1))
        ]

        for label, t in timestamps:
            img_name = f"{base_stem}_key_{label}.jpg"
            img_path = parent / img_name
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", f"{t:.3f}",
                "-i", str(clip_path),
                "-vframes", "1",
                "-q:v", "2",
                "-y",
                str(img_path)
            ]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0 and img_path.exists():
                key_frames.append(img_name)

        return key_frames

    def process_clip_request(
        self,
        req: ClipRequest,
        has_gap_fn: Optional[Any] = None,
        source_file: Optional[Path] = None,
        source_start_ms: Optional[int] = None,
        db_conn: Optional[Any] = None
    ) -> ClipResult:
        """Execute full clip cutting workflow."""
        clip_id = req.clip_id or str(ulid.ULID())
        now_ms = self.clock.now_ms()

        # Compute exact time window
        win_start, win_end, duration_s = compute_clip_window(
            kind=req.kind,
            start_ts_ms=req.start_ts_ms,
            end_ts_ms=req.end_ts_ms,
            pre_roll_s=req.pre_roll_s,
            hold_s=req.hold_s,
            max_clip_min=req.max_clip_min,
            anchor_ts_ms=req.anchor_ts_ms,
            sighting_length_s=req.sighting_length_s,
            sighting_pre_s=req.sighting_pre_s
        )

        # Date hierarchy path: data/clips/<yyyy>/<mm>/<dd>/<camera>/<id>.mp4
        dt = datetime.fromtimestamp(win_start / 1000.0, tz=timezone.utc)
        sub_dir = self.clips_dir / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d") / req.camera_id
        final_mp4 = sub_dir / f"{clip_id}.mp4"
        sidecar_json = sub_dir / f"{clip_id}.meta.json"

        # Check for recording gap
        has_gap = has_gap_fn(win_start, win_end) if has_gap_fn else False

        cut_success = False
        if source_file is not None and source_file.exists():
            # Batch mode: cut directly from file
            base_t = source_start_ms or req.start_ts_ms
            offset_s = max(0.0, (win_start - base_t) / 1000.0)
            cut_success = self.cut_clip_from_file(source_file, final_mp4, offset_s, duration_s)
        else:
            # Live mode: cut from continuous segments
            segments = self.find_covering_segments(req.camera_id, win_start, win_end)
            cut_success = self.cut_clip_from_segments(segments, final_mp4, win_start, duration_s)

        if not cut_success:
            status = "needs_repair"
            sha256 = ""
            size_bytes = 0
            key_frames = []
        else:
            status = "incomplete" if has_gap else "ready"
            sha256 = compute_sha256(final_mp4)
            size_bytes = final_mp4.stat().st_size
            key_frames = self.extract_key_frames(final_mp4, duration_s)

        # Write sidecar JSON
        sidecar_data = {
            "id": clip_id,
            "kind": req.kind,
            "camera_id": req.camera_id,
            "path": str(final_mp4),
            "sidecar_path": str(sidecar_json),
            "start_ts": win_start,
            "end_ts": win_end,
            "duration_s": duration_s,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "status": status,
            "key_frames": key_frames,
            "retention_class": req.retention_class,
            "created_at": now_ms,
            "metadata": req.metadata
        }

        sub_dir.mkdir(parents=True, exist_ok=True)
        with open(sidecar_json, "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, indent=2)

        # Update SQLite if db connection provided
        if db_conn is not None:
            try:
                db_conn.execute(
                    """
                    INSERT INTO clips (
                        id, kind, camera_id, path, sidecar_path, start_ts, end_ts,
                        duration_s, size_bytes, sha256, status, retention_class, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        path=excluded.path,
                        sidecar_path=excluded.sidecar_path,
                        status=excluded.status,
                        sha256=excluded.sha256,
                        size_bytes=excluded.size_bytes,
                        duration_s=excluded.duration_s
                    """,
                    (
                        clip_id, req.kind, req.camera_id, str(final_mp4), str(sidecar_json),
                        win_start, win_end, duration_s, size_bytes, sha256, status,
                        req.retention_class, now_ms
                    )
                )
                db_conn.commit()
            except Exception as e:
                logger.error(f"Failed to record clip in database: {e}")

        return ClipResult(
            clip_id=clip_id,
            kind=req.kind,
            camera_id=req.camera_id,
            path=str(final_mp4),
            sidecar_path=str(sidecar_json),
            start_ts=win_start,
            end_ts=win_end,
            duration_s=duration_s,
            size_bytes=size_bytes,
            sha256=sha256,
            status=status,
            key_frames=key_frames,
            created_at=now_ms
        )

