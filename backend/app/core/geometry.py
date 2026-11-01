"""Geometry primitives for zones and tracks.

Pure geometry logic: point-in-polygon (foot point convention),
line crossings with directional orientation, coordinate transformations.
No external I/O, no DB, no network, no clocks.
"""



def get_foot_point(xyxy: tuple[float, float, float, float]) -> tuple[float, float]:
    """Calculate the bottom-center foot point of a bounding box (x1, y1, x2, y2)."""
    x1, _, x2, y2 = xyxy
    return ((x1 + x2) / 2.0, y2)


def denormalize_points(
    points: list[tuple[float, float]],
    width: int,
    height: int
) -> list[tuple[float, float]]:
    """Convert normalized (0..1) coordinates to full-resolution pixel coordinates."""
    return [(float(x) * width, float(y) * height) for x, y in points]


def normalize_points(
    points: list[tuple[float, float]],
    width: int,
    height: int
) -> list[tuple[float, float]]:
    """Convert pixel coordinates to normalized (0..1) coordinates."""
    if width <= 0 or height <= 0:
        return [(0.0, 0.0) for _ in points]
    return [(float(x) / width, float(y) / height) for x, y in points]


def is_point_on_segment(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
    tol: float = 1e-6
) -> bool:
    """Check if point (px, py) lies on line segment (x1, y1)-(x2, y2)."""
    # Check bounding box
    if not (min(x1, x2) - tol <= px <= max(x1, x2) + tol and
            min(y1, y2) - tol <= py <= max(y1, y2) + tol):
        return False
    # Cross product for collinearity
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    return abs(cross) <= tol * (max(abs(x2 - x1), abs(y2 - y1), 1.0))


def point_in_polygon(
    point: tuple[float, float],
    polygon: list[tuple[float, float]]
) -> bool:
    """Check if point is inside or on the boundary of a polygon.
    
    Uses ray-casting with explicit boundary inclusion (boundary counted inside).
    Polygon points are [(x, y), ...] in order.
    """
    if len(polygon) < 3:
        return False

    px, py = point
    n = len(polygon)

    # First check if point lies directly on any boundary segment
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if is_point_on_segment(px, py, x1, y1, x2, y2):
            return True

    # Ray-casting algorithm
    inside = False
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]

        # Ray to the right (+x)
        if ((y1 > py) != (y2 > py)):
            # Find x coordinate of intersection with horizontal line y = py
            intersect_x = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < intersect_x:
                inside = not inside

    return inside


def line_side(
    p1: tuple[float, float],
    p2: tuple[float, float],
    pt: tuple[float, float]
) -> int:
    """Determine which side of directed line P1->P2 point pt is on.
    
    Screen coordinates (y down):
    Vector V = P2 - P1 = (dx, dy)
    Vector W = pt - P1 = (wx, wy)
    Cross product = dx * wy - dy * wx
    
    Returns:
       1 if positive side (right of vector in screen coordinates)
      -1 if negative side (left of vector in screen coordinates)
       0 if collinear / on line
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    wx = pt[0] - p1[0]
    wy = pt[1] - p1[1]
    
    cross = dx * wy - dy * wx
    if abs(cross) < 1e-7:
        return 0
    return 1 if cross > 0 else -1


def segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float]
) -> bool:
    """Check if line segment a1-a2 intersects line segment b1-b2."""
    def ccw(p1, p2, p3):
        return (p3[1] - p1[1]) * (p2[0] - p1[0]) > (p2[1] - p1[1]) * (p3[0] - p1[0])

    s1 = line_side(b1, b2, a1)
    s2 = line_side(b1, b2, a2)
    s3 = line_side(a1, a2, b1)
    s4 = line_side(a1, a2, b2)

    # Straddle checks
    if s1 != s2 and s3 != s4:
        return True

    # Collinear/touching checks
    if is_point_on_segment(a1[0], a1[1], b1[0], b1[1], b2[0], b2[1]):
        return True
    if is_point_on_segment(a2[0], a2[1], b1[0], b1[1], b2[0], b2[1]):
        return True
    if is_point_on_segment(b1[0], b1[1], a1[0], a1[1], a2[0], a2[1]):
        return True
    return is_point_on_segment(b2[0], b2[1], a1[0], a1[1], a2[0], a2[1])


def check_line_crossing(
    p1: tuple[float, float],
    p2: tuple[float, float],
    prev_pt: tuple[float, float],
    curr_pt: tuple[float, float],
    direction: str = "in"
) -> tuple[bool, str | None]:
    """Check if movement from prev_pt to curr_pt crossed line segment P1->P2.
    
    Per docs/04 s1:
    - Direction 'in': movement from negative side to positive side.
    - Direction 'out': movement from positive side to negative side.
    - Direction 'both': crossing in either direction.
    
    Returns:
        (crossed: bool, observed_direction: Optional['in' | 'out'])
    """
    if prev_pt == curr_pt:
        return False, None

    # Check if movement segment actually intersects the line segment
    if not segments_intersect(prev_pt, curr_pt, p1, p2):
        return False, None

    prev_s = line_side(p1, p2, prev_pt)
    curr_s = line_side(p1, p2, curr_pt)

    observed: str | None = None
    if prev_s < 0 and curr_s >= 0:
        observed = "in"
    elif prev_s >= 0 and curr_s < 0:
        observed = "out"
    elif prev_s == 0 and curr_s > 0:
        observed = "in"
    elif prev_s == 0 and curr_s < 0:
        observed = "out"

    if observed is None:
        return False, None

    if direction == "both" or direction == observed:
        return True, observed
    else:
        return False, observed


def validate_polygon(points: list[tuple[float, float]]) -> tuple[bool, str]:
    """Validate polygon points (3 to 20 points, non-self-intersecting)."""
    n = len(points)
    if n < 3:
        return False, f"Polygon must have at least 3 points, got {n}"
    if n > 20:
        return False, f"Polygon cannot exceed 20 points, got {n}"

    # Check for self-intersection
    for i in range(n):
        a1 = points[i]
        a2 = points[(i + 1) % n]
        for j in range(i + 2, n):
            if (i == 0 and j == n - 1):
                continue  # adjacent segments sharing vertex
            b1 = points[j]
            b2 = points[(j + 1) % n]
            if segments_intersect(a1, a2, b1, b2):
                return False, f"Polygon self-intersects between edges ({i},{i+1}) and ({j},{(j+1)%n})"

    return True, "valid"
