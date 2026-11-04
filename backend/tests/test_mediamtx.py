import pytest
from app.services.mediamtx import sanitize_path_name, MediaMTXService


def test_sanitize_path_name():
    assert sanitize_path_name("cam01") == "cam01"
    assert sanitize_path_name("phone_cam01") == "phone_cam01"
    assert sanitize_path_name("Main Gate Entrance") == "Main_Gate_Entrance"
    assert sanitize_path_name("camera#1/test") == "camera_1_test"


def test_is_local_stream():
    service = MediaMTXService()
    assert service.is_local_stream("rtsp://localhost:8554/cam01") is True
    assert service.is_local_stream("rtsp://127.0.0.1:8554/cam02") is True
    assert service.is_local_stream("rtsp://192.168.1.40:8554/live") is False
    assert service.is_local_stream("rtsp://admin:pass@10.0.0.5:554/stream1") is False


def test_sync_camera_graceful_on_unreachable_api():
    service = MediaMTXService(api_url="http://127.0.0.1:19999", timeout=0.1)
    # Should not throw exception when MediaMTX is unreachable
    assert service.sync_camera("test_cam", "rtsp://192.168.1.50:554/live") is False
    assert service.remove_camera("test_cam") is False
