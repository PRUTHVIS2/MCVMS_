from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

@dataclass(frozen=True)
class Detection:
    cls: str
    conf: float
    xyxy: Tuple[float, float, float, float]
    keypoints: Optional[Any] = None

@dataclass(frozen=True)
class TrackedObject:
    track_id: int
    cls: str
    conf: float
    xyxy: Tuple[float, float, float, float]
    foot_point: Tuple[float, float]
    ts_ms: int
    keypoints: Optional[Any] = None

@dataclass(frozen=True)
class TrackedFrame:
    camera_id: str
    ts_ms: int
    frame_size: Tuple[int, int]
    objects: List[TrackedObject]

@dataclass(frozen=True)
class AttrValue:
    value: Any
    conf: float
    state: str  # 'known' or 'unknown'
    n_obs: int
    updated_ms: int

@dataclass(frozen=True)
class TrackAttributes:
    track_id: int
    kind: str  # 'vehicle' or 'person'
    attrs: Dict[str, AttrValue] = field(default_factory=dict)
