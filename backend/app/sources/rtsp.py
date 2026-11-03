import ctypes
import logging
import os
import sys
import threading
import time
from typing import Optional, Tuple

import cv2

from app.core.clock import Clock
from app.core.health import record_decode_error

logger = logging.getLogger(__name__)


_env_set = False

def _set_rtsp_tcp_env() -> None:
    """Force RTSP over TCP and a 5s connect timeout in OpenCV FFMPEG backend."""
    global _env_set
    if not _env_set:
        val = "rtsp_transport;tcp|timeout;5000000"
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = val
        if sys.platform == "win32":
            try:
                ctypes.windll.kernel32.SetEnvironmentVariableW("OPENCV_FFMPEG_CAPTURE_OPTIONS", val)
            except Exception as e:
                logger.debug(f"Could not set Win32 environment variable: {e}")
        _env_set = True


class RTSPSource:
    def __init__(
        self,
        url: str,
        clock: Clock,
        frozen_timeout: float = 30.0,
        camera_id: Optional[str] = None
    ):
        self.url = url
        self.clock = clock
        self.frozen_timeout = frozen_timeout
        self.camera_id = camera_id

        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame = None
        self.latest_ts = 0
        self.lock = threading.Lock()

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.backoff_sequence = [1, 2, 4, 8, 16, 32, 60]
        self.backoff_idx = 0

        self.last_frame_received_at = 0.0
        self.online = False
        self._connected_evt = threading.Event()

        # Stream properties
        self.width: Optional[int] = None
        self.height: Optional[int] = None
        self.fps: Optional[float] = None

        # Decode error tracking
        self.decode_errors = 0
        self._last_decode_warn_ts = 0.0

    def start(self) -> None:
        self.running = True
        self._connected_evt.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._connected_evt.wait(timeout=0.2)

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def get_latest(self) -> Optional[Tuple[object, int]]:
        with self.lock:
            return (self.latest_frame.copy(), self.latest_ts) if self.latest_frame is not None else None

    def _run(self) -> None:
        while self.running:
            try:
                self._connect_and_read()
            except Exception as e:
                logger.error(f"RTSP error on {self.camera_id or self.url}: {e}")

            if not self.running:
                break

            self.online = False
            sleep_time = self.backoff_sequence[self.backoff_idx]
            self.backoff_idx = min(self.backoff_idx + 1, len(self.backoff_sequence) - 1)
            logger.info(f"Reconnecting to {self.url} in {sleep_time}s...")
            time.sleep(sleep_time)

    def _connect_and_read(self) -> None:
        _set_rtsp_tcp_env()
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to open stream {self.url}")

        self.backoff_idx = 0
        self.last_frame_received_at = self.clock.now_ms() / 1000.0
        self.online = True
        self._connected_evt.set()

        # Capture stream geometry & frame rate
        try:
            if hasattr(self.cap, "get"):
                w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                fps = self.cap.get(cv2.CAP_PROP_FPS)
                if isinstance(w, (int, float)) and int(w) > 0:
                    self.width = int(w)
                if isinstance(h, (int, float)) and int(h) > 0:
                    self.height = int(h)
                if isinstance(fps, (int, float)) and float(fps) > 0.0:
                    self.fps = float(fps)
        except Exception as e:
            logger.warning(f"Could not read stream properties for {self.camera_id or self.url}: {e}")

        while self.running:
            ret, frame = self.cap.read()
            now = self.clock.now_ms()
            now_sec = now / 1000.0

            is_empty = hasattr(frame, "size") and frame.size == 0
            if not ret or frame is None or is_empty:
                self.decode_errors += 1
                if self.camera_id:
                    record_decode_error(self.camera_id)

                if now_sec - self._last_decode_warn_ts >= 5.0:
                    self._last_decode_warn_ts = now_sec
                    logger.warning(
                        f"Camera {self.camera_id or self.url}: decode error count = {self.decode_errors}"
                    )

                if now_sec - self.last_frame_received_at > self.frozen_timeout:
                    logger.warning(f"Stream {self.url} frozen")
                    break

                time.sleep(0.01)
                continue

            self.last_frame_received_at = now_sec
            with self.lock:
                self.latest_frame = frame
                self.latest_ts = now

        if self.cap:
            self.cap.release()
            self.cap = None
