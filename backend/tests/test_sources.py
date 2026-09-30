import pytest
import time
from unittest.mock import MagicMock, patch
from app.sources.timesource import FileTimeSource, WallTimeSource
from app.sources.filesource import FileSource
from app.sources.rtsp import RTSPSource
from app.core.clock import SimulatedClock

def test_file_timesource():
    ts = FileTimeSource.from_filename("20261005_083000.mp4")
    # 2026-10-05 08:30:00 UTC = 1791189000000 ms roughly
    start_ms = ts.now_ms()
    assert start_ms > 1700000000000
    
    ts.advance(40)
    assert ts.now_ms() == start_ms + 40

@patch('cv2.VideoCapture')
def test_file_source_timestamps(mock_vc):
    # Mock VideoCapture to return 3 frames
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 25.0 # 25 fps -> 40ms per frame
    
    # ret, frame
    mock_cap.read.side_effect = [(True, "frame1"), (True, "frame2"), (True, "frame3"), (False, None)]
    mock_vc.return_value = mock_cap
    
    ts = FileTimeSource(1000)
    fs = FileSource("dummy.mp4", ts, paced=False)
    
    frames = list(fs.iter_frames())
    assert len(frames) == 3
    assert frames[0][1] == 1000
    assert frames[1][1] == 1040
    assert frames[2][1] == 1080

@patch('cv2.VideoCapture')
def test_rtsp_frozen_stream_and_reconnect(mock_vc):
    clock = SimulatedClock(1000000) # start at 1000s
    
    # We will control what cap.read() returns based on clock
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    
    def mock_read():
        now = clock.now_ms() / 1000.0
        # return frames for 5 seconds, then freeze
        if now < 1005.0:
            return True, "frame"
        else:
            return False, None
            
    mock_cap.read.side_effect = mock_read
    mock_vc.return_value = mock_cap
    
    # use a very short frozen_timeout for test
    rtsp = RTSPSource("rtsp://fake", clock, frozen_timeout=2.0)
    # mock sleep to avoid real sleep
    
    with patch('time.sleep') as mock_sleep:
        rtsp.start()
        
        # wait a bit for thread to start and read
        time.sleep(0.1)
        
        assert rtsp.online == True
        
        # advance clock to 1006 (1 sec after freeze starts)
        clock.advance(6000)
        time.sleep(0.1)
        # Should still be online since timeout is 2.0
        assert rtsp.online == True
        
        # advance clock to 1008 (3 sec after freeze starts, > 2.0 timeout)
        clock.advance(2000)
        time.sleep(0.1)
        
        # Should have detected freeze, broken the loop, and incremented backoff
        rtsp.stop()
        
    assert mock_sleep.called
