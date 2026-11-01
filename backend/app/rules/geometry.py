"""Geometry re-exports for the pure rules package."""

from app.core.geometry import (
    check_line_crossing,
    denormalize_points,
    get_foot_point,
    is_point_on_segment,
    line_side,
    normalize_points,
    point_in_polygon,
    segments_intersect,
    validate_polygon,
)

__all__ = [
    "check_line_crossing",
    "denormalize_points",
    "get_foot_point",
    "is_point_on_segment",
    "line_side",
    "normalize_points",
    "point_in_polygon",
    "segments_intersect",
    "validate_polygon",
]
