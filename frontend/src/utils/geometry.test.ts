import { describe, expect, it } from 'vitest';
import {
  distance,
  findClosestVertex,
  flipDirection,
  getLineDirectionArrow,
  isNormalized,
  toCanvasCoords,
  toNormalizedCoords,
  validateZonePoints,
} from './geometry';

describe('geometry utilities', () => {
  it('converts normalized coordinates to canvas coordinates and back', () => {
    const norm: [number, number] = [0.25, 0.5];
    const canvas = toCanvasCoords(norm, 800, 600);
    expect(canvas).toEqual([200, 300]);

    const reverted = toNormalizedCoords(canvas[0], canvas[1], 800, 600);
    expect(reverted).toEqual([0.25, 0.5]);
  });

  it('clamps normalized coordinates to [0, 1] range', () => {
    const clampedLower = toNormalizedCoords(-10, -50, 100, 100);
    expect(clampedLower).toEqual([0, 0]);

    const clampedUpper = toNormalizedCoords(150, 200, 100, 100);
    expect(clampedUpper).toEqual([1, 1]);
  });

  it('checks if coordinate is normalized', () => {
    expect(isNormalized([0.5, 0.5])).toBe(true);
    expect(isNormalized([0.0, 1.0])).toBe(true);
    expect(isNormalized([-0.1, 0.5])).toBe(false);
    expect(isNormalized([1.1, 0.5])).toBe(false);
  });

  it('calculates euclidean distance between canvas points', () => {
    expect(distance([0, 0], [3, 4])).toBe(5);
    expect(distance([100, 100], [100, 100])).toBe(0);
  });

  it('finds closest vertex within threshold radius', () => {
    const points: [number, number][] = [
      [0.1, 0.1], // canvas [100, 100] on 1000x1000
      [0.5, 0.5], // canvas [500, 500]
      [0.9, 0.9], // canvas [900, 900]
    ];

    // Click near [100, 100] -> index 0
    expect(findClosestVertex(points, [105, 98], 1000, 1000, 15)).toBe(0);

    // Click far away -> -1
    expect(findClosestVertex(points, [300, 300], 1000, 1000, 15)).toBe(-1);
  });

  it('cycles line direction properly on flip', () => {
    expect(flipDirection('in')).toBe('out');
    expect(flipDirection('out')).toBe('both');
    expect(flipDirection('both')).toBe('in');
    expect(flipDirection(null)).toBe('in');
  });

  it('computes line direction arrow vector', () => {
    const p1: [number, number] = [0.2, 0.5];
    const p2: [number, number] = [0.8, 0.5];

    const arrowIn = getLineDirectionArrow(p1, p2, 'in', 1000, 1000);
    expect(arrowIn).not.toBeNull();
    expect(arrowIn!.start).toEqual([500, 500]);
    // Arrow should point perpendicular to horizontal line
    expect(arrowIn!.end[0]).toBe(500);
    expect(arrowIn!.end[1]).toBeGreaterThan(500);

    const arrowBoth = getLineDirectionArrow(p1, p2, 'both', 1000, 1000);
    expect(arrowBoth).toBeNull();
  });

  it('validates polygon and line vertex counts', () => {
    // Polygon
    expect(validateZonePoints('polygon', [[0.1, 0.1], [0.5, 0.1]]).valid).toBe(false);
    expect(
      validateZonePoints('polygon', [
        [0.1, 0.1],
        [0.5, 0.1],
        [0.5, 0.5],
      ]).valid
    ).toBe(true);

    // Line
    expect(validateZonePoints('line', [[0.1, 0.1]]).valid).toBe(false);
    expect(
      validateZonePoints('line', [
        [0.1, 0.1],
        [0.1, 0.1],
      ]).valid
    ).toBe(false); // same point
    expect(
      validateZonePoints('line', [
        [0.1, 0.1],
        [0.5, 0.5],
      ]).valid
    ).toBe(true);
  });
});

