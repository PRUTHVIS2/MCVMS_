import numpy as np
from types import SimpleNamespace
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.engine.results import Boxes
import torch
from typing import List, Optional
from app.core.types import Detection, TrackedObject

class Tracker:
    def __init__(self, fps: int = 25):
        args = SimpleNamespace(
            track_high_thresh=0.25,
            track_low_thresh=0.1,
            new_track_thresh=0.25,
            track_buffer=30,
            match_thresh=0.8,
            gmc_method='sparseOptFlow',
            fuse_score=False
        )
        self.tracker = BYTETracker(args)
        self.frame_id = 0
        
    def update(self, detections: List[Detection], img: np.ndarray, ts_ms: int) -> List[TrackedObject]:
        self.frame_id += 1
        if not detections:
            # BYTETracker doesn't like empty boxes tensor sometimes, or we can just pass empty
            boxes_tensor = torch.empty((0, 6))
        else:
            # Map cls string back to an integer for the tracker
            # Actually, since we only have class names in Detection, we should map it to some dummy int,
            # or just use a hash, but we need consistency. We can just use the index of a list, but wait,
            # we can pass arbitrary floats as class ID to tracker and it preserves them (or casts to int).
            # We'll build a dynamic map or just use hash. A simple dict will do.
            class_map_inv = {"person": 0, "car": 2, "two_wheeler": 3, "bus": 5, "truck": 7}
            
            box_data = []
            for d in detections:
                cls_id = class_map_inv.get(d.cls, hash(d.cls) % 100)
                box_data.append([d.xyxy[0], d.xyxy[1], d.xyxy[2], d.xyxy[3], d.conf, cls_id])
                
            boxes_tensor = torch.tensor(box_data, dtype=torch.float32)
            
        boxes = Boxes(boxes_tensor, orig_shape=img.shape[:2])
        
        try:
            tracks = self.tracker.update(boxes, img=img)
        except Exception as e:
            # Fallback if tracker fails for some reason
            tracks = np.empty((0, 8))
            
        tracked_objects = []
        for t in tracks:
            # t: [x1, y1, x2, y2, track_id, score, cls, idx]
            x1, y1, x2, y2 = float(t[0]), float(t[1]), float(t[2]), float(t[3])
            track_id = int(t[4])
            score = float(t[5])
            cls_id = int(t[6])
            
            # Map back to class name
            cls_name = "unknown"
            class_map = {0: "person", 2: "car", 3: "two_wheeler", 5: "bus", 7: "truck"}
            if cls_id in class_map:
                cls_name = class_map[cls_id]
                
            # foot point (center of bottom edge)
            foot_point = ((x1 + x2) / 2.0, y2)
            
            # retrieve original keypoints if available
            idx = int(t[7])
            keypoints = None
            if idx < len(detections):
                keypoints = detections[idx].keypoints
                if cls_name == "unknown":
                    cls_name = detections[idx].cls
                
            tracked_objects.append(TrackedObject(
                track_id=track_id,
                cls=cls_name,
                conf=score,
                xyxy=(x1, y1, x2, y2),
                foot_point=foot_point,
                ts_ms=ts_ms,
                keypoints=keypoints
            ))
            
        return tracked_objects
