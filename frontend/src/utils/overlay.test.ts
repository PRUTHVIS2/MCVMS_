import { describe, it, expect, vi } from 'vitest';
import { scaleBox, scaleNormalizedPoint, getAttributeChips, drawZone } from './overlay';
import type { Track, Zone } from '../types';

describe('overlay coordinate and scaling maths', () => {
  it('correctly scales bounding box from source frame to canvas size', () => {
    // 1920x1080 frame scaled to 960x540 canvas (scale factor 0.5)
    const box: [number, number, number, number] = [100, 200, 500, 600];
    const frameSize: [number, number] = [1920, 1080];
    const canvasSize = { width: 960, height: 540 };

    const scaled = scaleBox(box, frameSize, canvasSize);
    expect(scaled.x).toBe(50);
    expect(scaled.y).toBe(100);
    expect(scaled.w).toBe(200);
    expect(scaled.h).toBe(200);
  });

  it('handles invalid or zero-sized frames safely', () => {
    const box: [number, number, number, number] = [10, 20, 30, 40];
    const scaled = scaleBox(box, [0, 0], { width: 100, height: 100 });
    expect(scaled).toEqual({ x: 0, y: 0, w: 0, h: 0 });
  });

  it('scales bounding box with 4:3 frame in 16:9 canvas using letterbox contentRect', () => {
    // 640x480 frame in 1600x900 canvas -> contentRect is x: 200, y: 0, w: 1200, h: 900
    const box: [number, number, number, number] = [0, 0, 320, 240];
    const frameSize: [number, number] = [640, 480];
    const canvasSize = { width: 1600, height: 900 };

    const scaled = scaleBox(box, frameSize, canvasSize);
    expect(scaled.x).toBe(200);
    expect(scaled.y).toBe(0);
    expect(scaled.w).toBe(600);
    expect(scaled.h).toBe(450);
  });

  it('correctly converts normalized coordinates [0..1] to canvas coordinates', () => {
    const pt: [number, number] = [0.25, 0.75];
    const canvasSize = { width: 800, height: 600 };

    const scaled = scaleNormalizedPoint(pt, canvasSize);
    expect(scaled.x).toBe(200);
    expect(scaled.y).toBe(450);
  });

  it('formats attribute chips correctly including unknown states', () => {
    const trackWithKnown: Track = {
      id: 1,
      class: 'car',
      conf: 0.92,
      bbox: [10, 10, 50, 50],
      foot_point: [30, 50],
      attributes: {
        colour: { value: 'white', conf: 0.85, state: 'known' },
        plate: { value: 'KA05AB1234', conf: 0.95, state: 'known' },
      },
    };

    const chips = getAttributeChips(trackWithKnown);
    expect(chips).toContain('white');
    expect(chips).toContain('KA05AB1234');

    const trackWithUnknownPlate: Track = {
      id: 2,
      class: 'car',
      conf: 0.88,
      bbox: [10, 10, 50, 50],
      foot_point: [30, 50],
      attributes: {
        plate: { value: '', conf: 0.1, state: 'unknown' },
      },
    };

    const unknownChips = getAttributeChips(trackWithUnknownPlate);
    expect(unknownChips).toContain('plate unknown');

    const trackWithNoId: Track = {
      id: 3,
      class: 'person',
      conf: 0.89,
      bbox: [10, 10, 50, 100],
      foot_point: [30, 100],
      attributes: {
        id_state: { value: 'not_wearing', conf: 0.9, state: 'known' },
      },
    };

    const noIdChips = getAttributeChips(trackWithNoId);
    expect(noIdChips).toContain('no ID?');
  });

  it('draws normal zone with dotted grey stroke and proper dash pattern', () => {
    const normalZone: Zone = {
      id: 'z_normal_01',
      camera_id: 'cam01',
      name: 'Driveway Normal',
      kind: 'normal',
      shape: 'polygon',
      points: [
        [0.1, 0.1],
        [0.8, 0.1],
        [0.8, 0.8],
        [0.1, 0.8],
      ],
      is_read_area: false,
      enabled: true,
      created_at: 1793668180000,
      updated_at: 1793668180000,
    };

    const setLineDashSpy = vi.fn();
    const mockCtx = {
      save: vi.fn(),
      restore: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      stroke: vi.fn(),
      fillRect: vi.fn(),
      fillText: vi.fn(),
      measureText: vi.fn().mockReturnValue({ width: 60 }),
      setLineDash: setLineDashSpy,
      strokeStyle: '',
      fillStyle: '',
      lineWidth: 0,
      font: '',
    } as unknown as CanvasRenderingContext2D;

    drawZone(mockCtx, normalZone, { width: 1000, height: 1000 });

    // Dotted grey styling for normal zones
    expect(mockCtx.strokeStyle).toBe('#9ca3af');
    expect(mockCtx.lineWidth).toBe(1.5);
    expect(setLineDashSpy).toHaveBeenCalledWith([2, 4]);
  });

  it('draws special zone with dashed amber stroke and thicker line', () => {
    const specialZone: Zone = {
      id: 'z_special_01',
      camera_id: 'cam01',
      name: 'Exit gate line',
      kind: 'special',
      shape: 'line',
      points: [
        [0.136, 0.85],
        [0.965, 0.525],
      ],
      direction: 'in',
      is_read_area: false,
      enabled: true,
      created_at: 1793670708000,
      updated_at: 1793670708000,
    };

    const setLineDashSpy = vi.fn();
    const mockCtx = {
      save: vi.fn(),
      restore: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      stroke: vi.fn(),
      fillRect: vi.fn(),
      fillText: vi.fn(),
      arc: vi.fn(),
      measureText: vi.fn().mockReturnValue({ width: 60 }),
      setLineDash: setLineDashSpy,
      strokeStyle: '',
      fillStyle: '',
      lineWidth: 0,
      font: '',
    } as unknown as CanvasRenderingContext2D;

    drawZone(mockCtx, specialZone, { width: 1000, height: 1000 });

    // Dashed amber styling for special zones
    expect(mockCtx.strokeStyle).toBe('#f59e0b');
    expect(mockCtx.lineWidth).toBe(2);
    expect(setLineDashSpy).toHaveBeenCalledWith([6, 6]);
  });
});

