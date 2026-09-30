import time


class Clock:
    def now_ms(self) -> int:
        return int(time.time() * 1000)

class SimulatedClock(Clock):
    def __init__(self, start_ms: int = 0):
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int):
        self._now += ms
