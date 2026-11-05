import ctypes
import logging
import os
import sys
import threading
import time
from typing import Optional, Tuple

import cv2

from app.core.clock import Clock
from app.core.health import record_decode_error, record_dropped_frame

logger = logging.getLogger(__name__)


_env_set = False

def _set_rtsp_tcp_env() -> None:
    """Force RTSP over TCP, low-delay unbuffered playback and 2.5s connect timeout in OpenCV FFMPEG backend."""
    global _env_set
    if not _env_set:
        val = "rtsp_transport;tcp|timeout;2500000|fflags;nobuffer|flags;low_delay|max_delay;0"
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
        self._stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.backoff_sequence = [1, 2, 4, 8, 16, 32, 60]
        self.backoff_idx = 0

        self.last_frame_received_at = 0.0
        self.online = False
        self._connected_evt = threading.Event()
        self._frame_consumed = True
        self.dropped_frames = 0

        # Stream properties
        self.width: Optional[int] = None
        self.height: Optional[int] = None
        self.fps: Optional[float] = None

        # Decode error tracking
        self.decode_errors = 0
        self._last_decode_warn_ts = 0.0

    def start(self) -> None:
        self.running = True
        self._stop_event.clear()
        self._connected_evt.clear()
        thread_name = f"rtsp-reader-{self.camera_id or 'unknown'}"
        self.thread = threading.Thread(target=self._run, name=thread_name, daemon=True)
        self.thread.start()
        self._connected_evt.wait(timeout=0.2)

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        cap_to_release = None
        with self.lock:
            cap_to_release = self.cap
            self.cap = None
        if cap_to_release:
            try:
                cap_to_release.release()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def get_latest(self) -> Optional[Tuple[object, int]]:
        with self.lock:
            if self.latest_frame is None:
                return None
            self._frame_consumed = True
            return (self.latest_frame.copy(), self.latest_ts)

    def _run(self) -> None:
        while self.running and not self._stop_event.is_set():
            try:
                self._connect_and_read()
            except Exception as e:
                logger.error(f"RTSP error on {self.camera_id or self.url}: {e}")

            if not self.running or self._stop_event.is_set():
                break

            self.online = False
            sleep_time = self.backoff_sequence[self.backoff_idx]
            self.backoff_idx = min(self.backoff_idx + 1, len(self.backoff_sequence) - 1)
            logger.info(f"Reconnecting to {self.url} in {sleep_time}s...")
            if self._stop_event.wait(timeout=sleep_time):
                break

    def _connect_and_read(self) -> None:
        _set_rtsp_tcp_env()
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open stream {self.url}")

        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception as e:
            logger.debug(f"Could not set CAP_PROP_BUFFERSIZE: {e}")

        with self.lock:
            self.cap = cap

        self.backoff_idx = 0
        self.last_frame_received_at = self.clock.now_ms() / 1000.0
        self.online = True
        self._connected_evt.set()

        # Capture stream geometry & frame rate
        try:
            if hasattr(cap, "get"):
                w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                fps = cap.get(cv2.CAP_PROP_FPS)
                if isinstance(w, (int, float)) and int(w) > 0:
                    self.width = int(w)
                if isinstance(h, (int, float)) and int(h) > 0:
                    self.height = int(h)
                if isinstance(fps, (int, float)) and float(fps) > 0.0:
                    self.fps = float(fps)
        except Exception as e:
            logger.warning(f"Could not read stream properties for {self.camera_id or self.url}: {e}")

        while self.running and not self._stop_event.is_set():
            ret, frame = cap.read()
            capture_ts = self.clock.now_ms()
            now_sec = capture_ts / 1000.0

            is_empty = hasattr(frame, "size") and frame.size == 0
            if not ret or frame is None or is_empty:
                if not self.running or self._stop_event.is_set():
                    break
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
                if self.latest_frame is not None and not self._frame_consumed:
                    self.dropped_frames += 1
                    if self.camera_id:
                        record_dropped_frame(self.camera_id, 1)

                self.latest_frame = frame
                self.latest_ts = capture_ts
                self._frame_consumed = False

        with self.lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
