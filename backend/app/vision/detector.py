import logging
import threading
from pathlib import Path

import torch
from ultralytics import YOLO

from app.config import config
from app.core.types import Detection

logger = logging.getLogger(__name__)

class Detector:
    def __init__(
        self,
        model_path: str | None = None,
        imgsz: int = 640,
        class_map: dict[int, str] | None = None
    ):
        self.imgsz = imgsz
        self._lock = threading.Lock()

        if model_path is None:
            model_path = config.models.get("vehicle_detector", "yolo11n.pt")
            configured_model = True
        else:
            configured_model = (
                model_path == config.models.get("vehicle_detector")
                or Path(model_path).name == Path(config.models.get("vehicle_detector", "")).name
            )

        path_obj = Path(model_path)
        if not path_obj.exists():
            candidate = Path(__file__).resolve().parent.parent.parent / model_path
            if candidate.exists():
                path_obj = candidate
            else:
                candidate_root = Path(__file__).resolve().parent.parent.parent.parent / model_path
                if candidate_root.exists():
                    path_obj = candidate_root

        self.model_path = str(path_obj)

        try:
            self.model = YOLO(self.model_path)
            # Device handling with warning
            if torch.cuda.is_available():
                self.model.to('cuda')
                logger.info(f"Detector loaded on CUDA: {self.model_path}")
            else:
                logger.warning("CUDA not available. Detector loaded on CPU. This will be slow!")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise

        if class_map is None:
            raw_map = config.models.get("class_map")
            if configured_model and raw_map:
                self.class_map = {int(k): str(v) for k, v in raw_map.items()}
            else:
                # Default COCO fallback
                self.class_map = {
                    0: "person",
                    2: "car",
                    3: "two_wheeler",
                    5: "bus",
                    7: "truck"
                }
        else:
            self.class_map = {int(k): str(v) for k, v in class_map.items()}
        
    def detect(self, frames, conf: float = 0.25):
        # frames can be a single frame or a list of frames
        is_single = not isinstance(frames, list)
        if is_single:
            frames = [frames]
            
        with self._lock:
            # YOLO handles GPU inference optimizations natively
            results = self.model.predict(frames, imgsz=self.imgsz, verbose=False, conf=conf, classes=list(self.class_map.keys()))
        
        batch_detections = []
        for result in results:
            detections = []
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    cls_id = int(box.cls.item())
                    if cls_id not in self.class_map:
                        continue
                    
                    class_name = self.class_map[cls_id]
                    c = float(box.conf.item())
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    keypoints = None
                    if result.keypoints is not None:
                        pass
                        
                    detections.append(Detection(
                        cls=class_name,
                        conf=c,
                        xyxy=(x1, y1, x2, y2),
                        keypoints=keypoints
                    ))
            batch_detections.append(detections)
            
        return batch_detections[0] if is_single else batch_detections
