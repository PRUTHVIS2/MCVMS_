import time

from app.core.clock import Clock, SimulatedClock


def test_clock():
    clock = Clock()
    now1 = clock.now_ms()
    time.sleep(0.01)
    now2 = clock.now_ms()
    assert now2 >= now1

def test_simulated_clock():
    clock = SimulatedClock(1000)
    assert clock.now_ms() == 1000
    clock.advance(500)
    assert clock.now_ms() == 1500
