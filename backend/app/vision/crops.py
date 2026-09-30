import numpy as np

def crop_full_res(frame: np.ndarray, xyxy: tuple[float, float, float, float], pad_frac: float = 0.0) -> np.ndarray:
    """
    Crops a region from the full-resolution frame, with optional padding.
    """
    x1, y1, x2, y2 = xyxy
    h_orig, w_orig = frame.shape[:2]
    
    w = x2 - x1
    h = y2 - y1
    
    pad_w = w * pad_frac
    pad_h = h * pad_frac
    
    x1 = int(max(0, x1 - pad_w))
    y1 = int(max(0, y1 - pad_h))
    x2 = int(min(w_orig, x2 + pad_w))
    y2 = int(min(h_orig, y2 + pad_h))
    
    if x2 <= x1 or y2 <= y1:
        return np.array([])
        
    return frame[y1:y2, x1:x2].copy()
