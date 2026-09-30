import threading
import time
import cv2
import logging
from typing import Optional, Tuple
from app.sources.timesource import WallTimeSource
from app.core.clock import Clock

logger = logging.getLogger(__name__)

class RTSPSource:
    def __init__(self, url: str, clock: Clock, frozen_timeout: float = 30.0):
        self.url = url
        self.clock = clock
        self.frozen_timeout = frozen_timeout
        
        self.cap = None
        self.latest_frame = None
        self.latest_ts = 0
        self.lock = threading.Lock()
        
        self.running = False
        self.thread = None
        self.backoff_sequence = [1, 2, 4, 8, 16, 32, 60]
        self.backoff_idx = 0
        
        self.last_frame_received_at = 0
        self.online = False
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            
    def get_latest(self) -> Optional[Tuple[object, int]]:
        with self.lock:
            return (self.latest_frame.copy(), self.latest_ts) if self.latest_frame is not None else None
            
    def _run(self):
        while self.running:
            try:
                self._connect_and_read()
            except Exception as e:
                logger.error(f"RTSP error: {e}")
            
            if not self.running:
                break
                
            self.online = False
            sleep_time = self.backoff_sequence[self.backoff_idx]
            self.backoff_idx = min(self.backoff_idx + 1, len(self.backoff_sequence) - 1)
            logger.info(f"Reconnecting to {self.url} in {sleep_time}s...")
            time.sleep(sleep_time)
            
    def _connect_and_read(self):
        import os
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000"
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            raise RuntimeError("Failed to open stream")
            
        self.backoff_idx = 0
        self.last_frame_received_at = self.clock.now_ms() / 1000.0
        self.online = True
        
        while self.running:
            ret, frame = self.cap.read()
            now = self.clock.now_ms()
            now_sec = now / 1000.0
            
            if not ret:
                # Could be frozen or EOF
                if now_sec - self.last_frame_received_at > self.frozen_timeout:
                    logger.warning("Stream frozen")
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
