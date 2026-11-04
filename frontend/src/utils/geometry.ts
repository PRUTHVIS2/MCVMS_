import type { Direction, ZoneShape } from '../types';

export type Point = [number, number];

/**
 * Check if coordinates are normalized [0.0..1.0].
 */
export function isNormalized(p: Point): boolean {
  return p[0] >= 0 && p[0] <= 1 && p[1] >= 0 && p[1] <= 1;
}

/**
 * Convert normalized [0..1] points to canvas/pixel coordinates.
 */
export function toCanvasCoords(p: Point, width: number, height: number): Point {
  return [Math.round(p[0] * width), Math.round(p[1] * height)];
}

/**
 * Convert canvas/pixel coordinates to normalized [0..1] points clamped to [0, 1].
 */
export function toNormalizedCoords(x: number, y: number, width: number, height: number): Point {
  const normX = Math.max(0, Math.min(1, x / width));
  const normY = Math.max(0, Math.min(1, y / height));
  return [Number(normX.toFixed(4)), Number(normY.toFixed(4))];
}

/**
 * Euclidean distance between two points in canvas coordinates.
 */
export function distance(p1: Point, p2: Point): number {
  const dx = p1[0] - p2[0];
  const dy = p1[1] - p2[1];
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Find the closest vertex index to a given point within a threshold distance (px).
 * Returns -1 if no vertex is within the threshold.
 */
export function findClosestVertex(
  points: Point[],
  clickPoint: Point,
  canvasWidth: number,
  canvasHeight: number,
  thresholdPx = 12
): number {
  for (let i = 0; i < points.length; i++) {
    const canvasP = toCanvasCoords(points[i], canvasWidth, canvasHeight);
    if (distance(canvasP, clickPoint) <= thresholdPx) {
      return i;
    }
  }
  return -1;
}

/**
 * Flip line crossing direction.
 * Cycles or toggles: 'in' -> 'out' -> 'both' -> 'in'.
 */
export function flipDirection(dir: Direction | null | undefined): Direction {
  if (dir === 'in') return 'out';
  if (dir === 'out') return 'both';
  return 'in';
}

/**
 * Calculate perpendicular normal arrow vector for a line segment [p1, p2].
 * Returns arrow start, end, and arrowhead points.
 */
export function getLineDirectionArrow(
  p1: Point,
  p2: Point,
  direction: Direction | null | undefined,
  canvasWidth: number,
  canvasHeight: number
): { start: Point; end: Point } | null {
  if (!direction || direction === 'both') return null;

  const cp1 = toCanvasCoords(p1, canvasWidth, canvasHeight);
  const cp2 = toCanvasCoords(p2, canvasWidth, canvasHeight);

  const midX = (cp1[0] + cp2[0]) / 2;
  const midY = (cp1[1] + cp2[1]) / 2;

  const dx = cp2[0] - cp1[0];
  const dy = cp2[1] - cp1[1];
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1e-4) return null;

  // Unit perpendicular vector (pointing 90 degrees clockwise)
  let nx = -dy / len;
  let ny = dx / len;

  if (direction === 'out') {
    nx = -nx;
    ny = -ny;
  }

  const arrowLength = 24;
  return {
    start: [midX, midY],
    end: [midX + nx * arrowLength, midY + ny * arrowLength],
  };
}

/**
 * Validate shape points count.
 * Polygon requires >= 3 points.
 * Line requires exactly 2 points.
 */
export function validateZonePoints(shape: ZoneShape, points: Point[]): { valid: boolean; error?: string } {
  if (shape === 'line') {
    if (points.length !== 2) {
      return { valid: false, error: 'A line zone must contain exactly 2 points.' };
    }
    if (points[0][0] === points[1][0] && points[0][1] === points[1][1]) {
      return { valid: false, error: 'Start and end points of a line zone cannot be identical.' };
    }
  } else if (shape === 'polygon') {
    if (points.length < 3) {
      return { valid: false, error: 'A polygon zone requires at least 3 points.' };
    }
  }
  return { valid: true };
}

