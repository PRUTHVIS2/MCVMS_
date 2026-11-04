import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.core.types import Detection
from app.pipeline.analyzer import Analyzer
from app.vision.crops import crop_full_res
from app.vision.detector import Detector
from app.vision.tracker import Tracker


def test_crop_full_res():
    # create a pattern
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[10:20, 30:40] = 255
    
    # exact crop
    crop = crop_full_res(img, (30, 10, 40, 20))
    assert crop.shape == (10, 10, 3)
    assert np.all(crop == 255)
    
    # pad crop
    crop_pad = crop_full_res(img, (30, 10, 40, 20), pad_frac=0.1)
    # width is 10, pad 10% is 1. so x1=29, x2=41 -> width=12
    # height is 10, pad 10% is 1. so y1=9, y2=21 -> height=12
    assert crop_pad.shape == (12, 12, 3)
    
    # out of bounds crop
    crop_oob = crop_full_res(img, (95, 95, 105, 105))
    assert crop_oob.shape == (5, 5, 3)

class ScriptedDetector:
    def __init__(self, sequence):
        self.sequence = sequence
        self.idx = 0
        
    def detect(self, frame, conf=0.25):
        if self.idx < len(self.sequence):
            res = self.sequence[self.idx]
            self.idx += 1
            return res
        return []

def test_scripted_detector_analyzer():
    # scripted source
    source = MagicMock()
    # emit 3 frames
    frames = [
        (np.zeros((640,640,3), dtype=np.uint8), 1000),
        (np.zeros((640,640,3), dtype=np.uint8), 1040),
        (np.zeros((640,640,3), dtype=np.uint8), 1080),
        None
    ]
    def get_latest():
        if frames:
            return frames.pop(0)
        return None
    source.get_latest.side_effect = get_latest
    
    # scripted detector
    det = ScriptedDetector([
        [Detection("car", 0.9, (10, 10, 50, 50))],
        [Detection("car", 0.9, (15, 15, 55, 55))],
        [Detection("car", 0.9, (20, 20, 60, 60))]
    ])
    
    tracker = Tracker()
    analyzer = Analyzer("cam1", source, det, tracker)
    
    results = []
    def callback(tf):
        results.append(tf)
        
    analyzer.subscribe(callback)
    
    analyzer.start()
    time.sleep(0.5)
    analyzer.stop()
    
    assert len(results) == 3
    assert len(results[0].objects) == 1
    assert results[0].objects[0].cls == "car"
    assert results[0].objects[0].track_id > 0

def test_class_map_filters():
    # Only COCO classes like person, car, motorcycle, bus, truck are kept
    # 0: person, 2: car. For example, 1 is bicycle, should be dropped.
    # We test this by directly instantiating the real Detector but injecting fake results.
    det = Detector("yolo11n.pt")
    
    # mock the model output
    class MockBox:
        def __init__(self, cls, conf, xyxy):
            self.cls = torch.tensor([cls])
            self.conf = torch.tensor([conf])
            self.xyxy = torch.tensor([xyxy])
    class MockResult:
        def __init__(self):
            self.boxes = [
                MockBox(0, 0.9, [0,0,10,10]), # person
                MockBox(1, 0.9, [0,0,10,10]), # bicycle (dropped)
                MockBox(2, 0.9, [0,0,10,10])  # car
            ]
            self.keypoints = None
    
    det.model.predict = MagicMock(return_value=[MockResult()])
    
    detections = det.detect(np.zeros((10,10,3), dtype=np.uint8))
    assert len(detections) == 2
    assert detections[0].cls == "person"
    assert detections[1].cls == "car"

import torch


@pytest.mark.skipif(not torch.cuda.is_available(), reason="Requires GPU")
def test_analyzer_slow_consumer():
    source = MagicMock()
    # emit 3 frames
    frames = [
        (np.zeros((640,640,3), dtype=np.uint8), 1000),
        (np.zeros((640,640,3), dtype=np.uint8), 1040),
        (np.zeros((640,640,3), dtype=np.uint8), 1080),
        None
    ]
    def get_latest():
        if frames:
            return frames.pop(0)
        return None
    source.get_latest.side_effect = get_latest
    
    det = ScriptedDetector([[], [], []])
    tracker = Tracker()
    analyzer = Analyzer("cam1", source, det, tracker)
    
    results = []
    def slow_callback(tf):
        time.sleep(0.2)
        results.append(tf)
        
    analyzer.subscribe(slow_callback, maxsize=1)
    
    start = time.time()
    analyzer.start()
    time.sleep(0.6)
    analyzer.stop()
    
    # Analyzer should finish quickly, but the subscriber might drop some
    assert time.time() - start < 1.0 # The analyzer thread shouldn't be blocked by 0.6s total sleep
    # Because maxsize=1, and frames arrive instantly, we probably drop frames.
    assert len(results) < 3


def test_class_map_stub():
    """Test class map with a stub model:
    - Every mapped class ID exists in model's names.
    - Unmapped classes are ignored, not silently assigned.
    - Does not need GPU or real weights.
    """
    import threading
    from app.config import config

    # Stub model simulating the retrained detector's names
    stub_names = {
        0: 'person',
        1: 'bicycle',
        2: 'motorcycle',
        3: 'auto_rickshaw',
        4: 'car',
        5: 'bus',
        6: 'truck'
    }

    # Class map under test: either configured or target approved mapping
    cfg_class_map = config.models.get("class_map") or {
        0: "person",
        2: "two_wheeler",
        3: "auto_rickshaw",
        4: "car",
        5: "bus",
        6: "truck",
    }
    assert len(cfg_class_map) > 0, "class_map should not be empty"
    for cls_id, category in cfg_class_map.items():
        assert int(cls_id) in stub_names, f"Mapped class id {cls_id} not found in model names {stub_names}"
        assert category in ["person", "two_wheeler", "auto_rickshaw", "car", "bus", "truck"]

    # Unmapped class (e.g., 1: bicycle) should not be in the configured class map
    assert 1 not in [int(k) for k in cfg_class_map.keys()], "Class 1 (bicycle) should be ignored per approved configuration"

    # Create detector instance with stub model (no GPU or real weights needed)
    det = Detector.__new__(Detector)
    det.imgsz = 640
    det._lock = threading.Lock()
    det.model_path = "stub_model.pt"
    det.class_map = {int(k): str(v) for k, v in cfg_class_map.items()}

    mock_model = MagicMock()
    mock_model.names = stub_names
    det.model = mock_model

    # Simulate inference output containing:
    # - Mapped classes: 0 (person), 2 (motorcycle -> two_wheeler), 3 (auto_rickshaw), 4 (car), 5 (bus), 6 (truck)
    # - Unmapped classes: 1 (bicycle), 99 (unknown class)
    class MockBox:
        def __init__(self, cls, conf, xyxy):
            self.cls = torch.tensor([cls])
            self.conf = torch.tensor([conf])
            self.xyxy = torch.tensor([xyxy])

    class MockResult:
        def __init__(self):
            self.boxes = [
                MockBox(0, 0.95, [0, 0, 10, 10]),   # person -> mapped
                MockBox(1, 0.90, [0, 0, 10, 10]),   # bicycle -> unmapped / ignored
                MockBox(2, 0.92, [0, 0, 10, 10]),   # motorcycle -> mapped to two_wheeler
                MockBox(3, 0.88, [0, 0, 10, 10]),   # auto_rickshaw -> mapped to auto_rickshaw
                MockBox(4, 0.91, [0, 0, 10, 10]),   # car -> mapped to car
                MockBox(5, 0.89, [0, 0, 10, 10]),   # bus -> mapped to bus
                MockBox(6, 0.87, [0, 0, 10, 10]),   # truck -> mapped to truck
                MockBox(99, 0.99, [0, 0, 10, 10]),  # unknown -> unmapped / ignored
            ]
            self.keypoints = None

    mock_model.predict.return_value = [MockResult()]

    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    detections = det.detect(frame)

    # Exactly 6 mapped detections, unmapped 1 and 99 are ignored
    assert len(detections) == 6
    assert detections[0].cls == "person"
    assert detections[1].cls == "two_wheeler"
    assert detections[2].cls == "auto_rickshaw"
    assert detections[3].cls == "car"
    assert detections[4].cls == "bus"
    assert detections[5].cls == "truck"
