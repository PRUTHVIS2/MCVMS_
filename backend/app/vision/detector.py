import logging
import torch
from ultralytics import YOLO
from typing import List, Dict, Tuple
from app.core.types import Detection

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self, model_path: str = "yolo11n.pt", imgsz: int = 640):
        self.imgsz = imgsz
        try:
            self.model = YOLO(model_path)
            # Device handling with warning
            if torch.cuda.is_available():
                self.model.to('cuda')
                logger.info("Detector loaded on CUDA")
            else:
                logger.warning("CUDA not available. Detector loaded on CPU. This will be slow!")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise

        # Class map: COCO mapping (0: person, 2: car, 3: motorcycle, 5: bus, 7: truck)
        self.class_map: Dict[int, str] = {
            0: "person",
            2: "car",
            3: "two_wheeler",
            5: "bus",
            7: "truck"
        }
        
    def detect(self, frames, conf: float = 0.25):
        # frames can be a single frame or a list of frames
        is_single = not isinstance(frames, list)
        if is_single:
            frames = [frames]
            
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
