from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Detection:
    cls: str
    conf: float
    xyxy: tuple[float, float, float, float]
    keypoints: Any | None = None

@dataclass(frozen=True)
class TrackedObject:
    track_id: int
    cls: str
    conf: float
    xyxy: tuple[float, float, float, float]
    foot_point: tuple[float, float]
    ts_ms: int
    keypoints: Any | None = None

@dataclass(frozen=True)
class TrackedFrame:
    camera_id: str
    ts_ms: int
    frame_size: tuple[int, int]
    objects: list[TrackedObject]

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
    attrs: dict[str, AttrValue] = field(default_factory=dict)
