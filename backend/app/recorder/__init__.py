"""Recorder package for continuous segmented recording and clip cutting."""

from app.recorder.ffmpeg_recorder import FFmpegRecorder, RecorderSupervisor
from app.recorder.clipper import (
    compute_clip_window,
    Clipper,
    ClipRequest,
    ClipResult
)

__all__ = [
    "FFmpegRecorder",
    "RecorderSupervisor",
    "compute_clip_window",
    "Clipper",
    "ClipRequest",
    "ClipResult"
]

