import time
from datetime import datetime, timezone
import re
from app.core.clock import Clock

class TimeSource:
    def now_ms(self) -> int:
        raise NotImplementedError

class WallTimeSource(TimeSource):
    def __init__(self, clock: Clock):
        self.clock = clock

    def now_ms(self) -> int:
        return self.clock.now_ms()

class FileTimeSource(TimeSource):
    """
    Given a start time, yields time monotonically incremented by frame time (e.g., 1/FPS)
    or just reads the exact timestamp associated with a file frame.
    For now, it will track an internal offset.
    """
    def __init__(self, start_ts_ms: int):
        self._current_ts = start_ts_ms
        self._start_ts = start_ts_ms
    
    def now_ms(self) -> int:
        return self._current_ts
        
    def advance(self, ms: int):
        self._current_ts += ms
        
    @classmethod
    def from_filename(cls, filename: str) -> "FileTimeSource":
        # extract YYYYMMDD_HHMMSS
        m = re.search(r"(\d{8}_\d{6})", filename)
        if m:
            dt = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
            # assuming UTC for simplicity, or local timezone
            ts_ms = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
            return cls(ts_ms)
        return cls(0)
