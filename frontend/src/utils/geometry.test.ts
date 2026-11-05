import { describe, expect, it } from 'vitest';
import {
  distance,
  findClosestVertex,
  fit,
  flipDirection,
  getLineDirectionArrow,
  isNormalized,
  normalizedToPixel,
  pixelToNormalized,
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
  describe('fit (getContentRect) and letterbox coordinate mapping', () => {
    it('computes correct contentRect with letterboxing/pillarboxing for 16:9 and 4:3 in wide, tall, and square containers', () => {
      // 16:9 frame (1920x1080) in wide container (1600x600 -> containerAspect ~2.67 > frameAspect ~1.78)
      // Pillarboxed: full height, centered horizontally
      const wide169 = fit(1600, 600, 1920, 1080);
      expect(wide169.height).toBe(600);
      expect(Math.round(wide169.width)).toBe(Math.round(600 * (16 / 9))); // ~1067
      expect(Math.round(wide169.x)).toBe(Math.round((1600 - wide169.width) / 2));
      expect(wide169.y).toBe(0);

      // 16:9 frame in tall container (800x1000 -> containerAspect 0.8 < 1.78)
      // Letterboxed: full width, centered vertically
      const tall169 = fit(800, 1000, 1920, 1080);
      expect(tall169.width).toBe(800);
      expect(Math.round(tall169.height)).toBe(450);
      expect(tall169.x).toBe(0);
      expect(tall169.y).toBe(275);

      // 16:9 frame in square container (1000x1000)
      const square169 = fit(1000, 1000, 1920, 1080);
      expect(square169.width).toBe(1000);
      expect(Math.round(square169.height)).toBe(563);
      expect(square169.x).toBe(0);
      expect(Math.round(square169.y)).toBe(219);

      // 4:3 frame (2560x1920) in wide container (1600x900 -> containerAspect 1.78 > 1.33)
      // Pillarboxed: full height, centered horizontally
      const wide43 = fit(1600, 900, 2560, 1920);
      expect(wide43.height).toBe(900);
      expect(wide43.width).toBe(1200);
      expect(wide43.x).toBe(200);
      expect(wide43.y).toBe(0);

      // 4:3 frame in tall container (600x900 -> containerAspect 0.67 < 1.33)
      // Letterboxed: full width, centered vertically
      const tall43 = fit(600, 900, 640, 480);
      expect(tall43.width).toBe(600);
      expect(tall43.height).toBe(450);
      expect(tall43.x).toBe(0);
      expect(tall43.y).toBe(225);

      // 4:3 frame in square container (1000x1000 -> containerAspect 1.0 < 1.33)
      const square43 = fit(1000, 1000, 4, 3);
      expect(square43.width).toBe(1000);
      expect(square43.height).toBe(750);
      expect(square43.x).toBe(0);
      expect(square43.y).toBe(125);
    });

    it('maps corners to letterbox boundaries and round-trips coordinates accurately', () => {
      const rect = fit(1600, 900, 2560, 1920); // 4:3 in 16:9 container -> x: 200, y: 0, w: 1200, h: 900

      // Corners
      const topLeft = normalizedToPixel([0, 0], rect);
      expect(topLeft).toEqual([200, 0]);

      const bottomRight = normalizedToPixel([1, 1], rect);
      expect(bottomRight).toEqual([1400, 900]);

      // Center
      const center = normalizedToPixel([0.5, 0.5], rect);
      expect(center).toEqual([800, 450]);

      // Round trip normalized -> pixel -> normalized
      const testPoints: [number, number][] = [
        [0, 0],
        [1, 1],
        [0.25, 0.75],
        [0.6, 0.4],
        [0.1234, 0.9876],
      ];

      for (const pt of testPoints) {
        const px = normalizedToPixel(pt, rect);
        const norm = pixelToNormalized(px[0], px[1], rect);
        expect(norm[0]).toBeCloseTo(pt[0], 3);
        expect(norm[1]).toBeCloseTo(pt[1], 3);
      }
    });

    it('clamps clicks in letterbox bars to [0, 1]', () => {
      const rect = fit(1600, 900, 2560, 1920); // x: 200, y: 0, w: 1200, h: 900 (bars on x: 0..200 and 1400..1600)

      // Click in left black bar
      const leftBar = pixelToNormalized(50, 450, rect);
      expect(leftBar[0]).toBe(0);
      expect(leftBar[1]).toBe(0.5);

      // Click in right black bar
      const rightBar = pixelToNormalized(1550, 450, rect);
      expect(rightBar[0]).toBe(1);
      expect(rightBar[1]).toBe(0.5);

      // Click outside top/bottom
      const tallRect = fit(600, 900, 640, 480); // x: 0, y: 225, w: 600, h: 450
      const topBar = pixelToNormalized(300, 50, tallRect);
      expect(topBar[0]).toBe(0.5);
      expect(topBar[1]).toBe(0);

      const bottomBar = pixelToNormalized(300, 850, tallRect);
      expect(bottomBar[0]).toBe(0.5);
      expect(bottomBar[1]).toBe(1);
    });
  });
});
