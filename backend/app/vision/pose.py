import logging
import torch
from ultralytics import YOLO
from typing import List
from app.core.types import Detection

logger = logging.getLogger(__name__)

class PoseDetector:
    def __init__(self, model_path: str = "yolo11n-pose.pt", imgsz: int = 640):
        self.imgsz = imgsz
        self.model = None
        self.model_path = model_path
        
    def _lazy_load(self):
        if self.model is None:
            try:
                self.model = YOLO(self.model_path)
                if torch.cuda.is_available():
                    self.model.to('cuda')
                    logger.info("Pose model loaded on CUDA")
                else:
                    logger.warning("CUDA not available. Pose model on CPU.")
            except Exception as e:
                logger.error(f"Failed to load Pose model: {e}")
                raise
                
    def detect(self, frame, conf: float = 0.25) -> List[Detection]:
        self._lazy_load()
        results = self.model(frame, imgsz=self.imgsz, verbose=False, conf=conf, classes=[0]) # Only person
        
        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
                
            # Keypoints: shape (N, 17, 2 or 3)
            keypoints = result.keypoints
            
            for i, box in enumerate(boxes):
                c = float(box.conf.item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                
                kp = None
                if keypoints is not None and keypoints.data is not None and len(keypoints.data) > i:
                    kp = keypoints.data[i].cpu().numpy()
                    
                detections.append(Detection(
                    cls="person",
                    conf=c,
                    xyxy=(x1, y1, x2, y2),
                    keypoints=kp
                ))
                
        return detections
