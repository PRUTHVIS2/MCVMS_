import threading
import time
import logging
import queue
from typing import Callable, List, Optional
from app.sources.rtsp import RTSPSource
from app.vision.detector import Detector
from app.vision.tracker import Tracker
from app.core.types import TrackedFrame

logger = logging.getLogger(__name__)

class Analyzer:
    def __init__(self, camera_id: str, source: RTSPSource, detector: Detector, tracker: Tracker):
        self.camera_id = camera_id
        self.source = source
        self.detector = detector
        self.tracker = tracker
        
        self.subscribers: List[tuple[Callable[[TrackedFrame], None], 'queue.Queue']] = []
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
    def subscribe(self, callback: Callable[[TrackedFrame], None], maxsize: int = 10):
        import queue
        q = queue.Queue(maxsize=maxsize)
        
        def worker():
            while self.running or not q.empty():
                try:
                    tf = q.get(timeout=0.1)
                    try:
                        callback(tf)
                    except Exception as e:
                        logger.error(f"Subscriber error: {e}")
                except queue.Empty:
                    pass
                    
        self.subscribers.append((callback, q))
        
    def start(self):
        self.running = True
        
        # Start subscriber threads
        for cb, q in self.subscribers:
            def worker(callback, sub_q):
                while self.running or not sub_q.empty():
                    try:
                        tf = sub_q.get(timeout=0.1)
                        try:
                            callback(tf)
                        except Exception as e:
                            logger.error(f"Subscriber error: {e}")
                    except queue.Empty:
                        pass
            
            t = threading.Thread(target=worker, args=(cb, q), daemon=True)
            t.start()
            
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            
    def _run(self):
        last_ts = 0
        while self.running:
            latest = self.source.get_latest()
            if not latest:
                time.sleep(0.01)
                continue
                
            frame, ts = latest
            if ts <= last_ts:
                time.sleep(0.01)
                continue
                
            last_ts = ts
            
            try:
                detections = self.detector.detect(frame)
                tracked_objects = self.tracker.update(detections, frame, ts)
                
                h, w = frame.shape[:2]
                tracked_frame = TrackedFrame(
                    camera_id=self.camera_id,
                    ts_ms=ts,
                    frame_size=(w, h),
                    objects=tracked_objects
                )
                
                import queue
                for cb, q in self.subscribers:
                    try:
                        q.put_nowait(tracked_frame)
                    except queue.Full:
                        try:
                            q.get_nowait()
                            q.put_nowait(tracked_frame)
                        except queue.Empty:
                            pass
                        
            except Exception as e:
                logger.error(f"Analyzer error on {self.camera_id}: {e}")
                time.sleep(0.1)
