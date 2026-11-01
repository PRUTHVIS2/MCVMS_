"""Unit tests for geometry primitives (pure, no GPU).

Tests point-in-polygon (foot point convention, boundary included),
line crossing directions (in, out, both, jitter, flip),
and coordinate denormalization.
"""

import pytest

from app.core.geometry import (
    check_line_crossing,
    denormalize_points,
    get_foot_point,
    line_side,
    normalize_points,
    point_in_polygon,
    validate_polygon,
)


def test_foot_point_calculation():
    # Box: x1=10, y1=20, x2=50, y2=100
    # Foot point is bottom-center: ((10+50)/2, 100) = (30, 100)
    box = (10.0, 20.0, 50.0, 100.0)
    foot = get_foot_point(box)
    assert foot == (30.0, 100.0)


def test_point_in_polygon_simple_square():
    # Square from (0,0) to (100,100)
    square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

    # Strictly inside
    assert point_in_polygon((50.0, 50.0), square) is True
    assert point_in_polygon((1.0, 1.0), square) is True
    assert point_in_polygon((99.0, 99.0), square) is True

    # Strictly outside
    assert point_in_polygon((-1.0, 50.0), square) is False
    assert point_in_polygon((101.0, 50.0), square) is False
    assert point_in_polygon((50.0, -1.0), square) is False
    assert point_in_polygon((50.0, 101.0), square) is False


def test_point_in_polygon_boundary_counted_inside():
    # Per docs/04 s1: boundary counted inside
    square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

    # On edges
    assert point_in_polygon((50.0, 0.0), square) is True
    assert point_in_polygon((100.0, 50.0), square) is True
    assert point_in_polygon((50.0, 100.0), square) is True
    assert point_in_polygon((0.0, 50.0), square) is True

    # On vertices
    assert point_in_polygon((0.0, 0.0), square) is True
    assert point_in_polygon((100.0, 0.0), square) is True
    assert point_in_polygon((100.0, 100.0), square) is True
    assert point_in_polygon((0.0, 100.0), square) is True


def test_point_in_polygon_concave():
    # L-shaped polygon
    l_shape = [
        (0.0, 0.0),
        (50.0, 0.0),
        (50.0, 50.0),
        (100.0, 50.0),
        (100.0, 100.0),
        (0.0, 100.0)
    ]
    # Inside L
    assert point_in_polygon((25.0, 25.0), l_shape) is True
    assert point_in_polygon((75.0, 75.0), l_shape) is True
    assert point_in_polygon((25.0, 75.0), l_shape) is True

    # In the excluded cutout of the L
    assert point_in_polygon((75.0, 25.0), l_shape) is False


def test_line_side():
    # Directed line from (0, 50) to (100, 50) - horizontal pointing right
    # Screen coordinates: y is down.
    # W = pt - P1. If pt has y > 50 (below line in screen), cross > 0 -> positive side (+1).
    # If pt has y < 50 (above line in screen), cross < 0 -> negative side (-1).
    p1 = (0.0, 50.0)
    p2 = (100.0, 50.0)

    # Point below line (y=60)
    assert line_side(p1, p2, (50.0, 60.0)) == 1

    # Point above line (y=40)
    assert line_side(p1, p2, (50.0, 40.0)) == -1

    # Point on line
    assert line_side(p1, p2, (50.0, 50.0)) == 0


def test_line_crossing_directions():
    # Gate line from (0, 50) to (100, 50)
    p1 = (0.0, 50.0)
    p2 = (100.0, 50.0)

    # 'in': from negative side (y=40) to positive side (y=60)
    prev_pt = (50.0, 40.0)
    curr_pt = (50.0, 60.0)

    crossed_in, d_in = check_line_crossing(p1, p2, prev_pt, curr_pt, direction="in")
    assert crossed_in is True
    assert d_in == "in"

    crossed_out, d_out = check_line_crossing(p1, p2, prev_pt, curr_pt, direction="out")
    assert crossed_out is False
    assert d_out == "in"

    crossed_both, d_both = check_line_crossing(p1, p2, prev_pt, curr_pt, direction="both")
    assert crossed_both is True
    assert d_both == "in"

    # 'out': from positive side (y=60) to negative side (y=40)
    prev_pt2 = (50.0, 60.0)
    curr_pt2 = (50.0, 40.0)

    crossed_out2, d2 = check_line_crossing(p1, p2, prev_pt2, curr_pt2, direction="out")
    assert crossed_out2 is True
    assert d2 == "out"

    crossed_in2, _ = check_line_crossing(p1, p2, prev_pt2, curr_pt2, direction="in")
    assert crossed_in2 is False


def test_line_crossing_flip():
    # If line endpoints are flipped: P1=(100, 50), P2=(0, 50)
    # The direction vectors and positive/negative sides flip accordingly
    p1 = (100.0, 50.0)
    p2 = (0.0, 50.0)

    # Movement from y=40 to y=60 is now 'out'
    prev_pt = (50.0, 40.0)
    curr_pt = (50.0, 60.0)

    crossed_out, d = check_line_crossing(p1, p2, prev_pt, curr_pt, direction="out")
    assert crossed_out is True
    assert d == "out"


def test_line_crossing_non_intersecting():
    # Gate line from (0, 50) to (100, 50)
    p1 = (0.0, 50.0)
    p2 = (100.0, 50.0)

    # Object crosses the infinite line at x=150 (outside the gate segment!)
    prev_pt = (150.0, 40.0)
    curr_pt = (150.0, 60.0)

    crossed, _ = check_line_crossing(p1, p2, prev_pt, curr_pt, direction="both")
    assert crossed is False


def test_line_crossing_jitter_and_tangential():
    p1 = (0.0, 50.0)
    p2 = (100.0, 50.0)

    # Moving parallel to line on one side
    prev_pt = (20.0, 40.0)
    curr_pt = (60.0, 40.0)
    crossed, _ = check_line_crossing(p1, p2, prev_pt, curr_pt, direction="both")
    assert crossed is False

    # Zero displacement
    crossed, _ = check_line_crossing(p1, p2, (50.0, 40.0), (50.0, 40.0), direction="both")
    assert crossed is False


def test_validate_polygon():
    # Valid triangle
    valid, msg = validate_polygon([(0, 0), (10, 0), (5, 10)])
    assert valid is True

    # Less than 3 points
    valid, msg = validate_polygon([(0, 0), (10, 0)])
    assert valid is False
    assert "at least 3" in msg

    # More than 20 points
    too_many = [(float(i), float(i)) for i in range(21)]
    valid, msg = validate_polygon(too_many)
    assert valid is False
    assert "cannot exceed 20" in msg

    # Self-intersecting figure-eight polygon
    figure_8 = [(0, 0), (10, 10), (10, 0), (0, 10)]
    valid, msg = validate_polygon(figure_8)
    assert valid is False
    assert "self-intersects" in msg


def test_denormalize_and_normalize_points():
    norm_pts = [(0.1, 0.2), (0.5, 0.8)]
    w, h = 1920, 1080

    pixel_pts = denormalize_points(norm_pts, w, h)
    assert pixel_pts == [(192.0, 216.0), (960.0, 864.0)]

    re_norm = normalize_points(pixel_pts, w, h)
    assert pytest.approx(re_norm[0][0]) == 0.1
    assert pytest.approx(re_norm[0][1]) == 0.2
    assert pytest.approx(re_norm[1][0]) == 0.5
    assert pytest.approx(re_norm[1][1]) == 0.8
