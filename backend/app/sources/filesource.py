import cv2
import time
from typing import Generator, Tuple
from app.sources.timesource import FileTimeSource

class FileSource:
    def __init__(self, filepath: str, time_source: FileTimeSource, paced: bool = False):
        self.filepath = filepath
        self.time_source = time_source
        self.paced = paced
        self.cap = cv2.VideoCapture(self.filepath)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open {filepath}")
        
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 25.0
            
        self.frame_time_ms = int(1000.0 / self.fps)
        
    def iter_frames(self) -> Generator[Tuple[object, int], None, None]:
        while True:
            start_t = time.time()
            ret, frame = self.cap.read()
            if not ret:
                break
                
            ts = self.time_source.now_ms()
            yield frame, ts
            
            self.time_source.advance(self.frame_time_ms)
            
            if self.paced:
                elapsed = time.time() - start_t
                sleep_s = (self.frame_time_ms / 1000.0) - elapsed
                if sleep_s > 0:
                    time.sleep(sleep_s)
                    
        self.cap.release()
