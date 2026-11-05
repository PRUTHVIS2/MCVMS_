import type { Track, Zone } from '../types';
import { fit, type ContentRect } from './geometry';

export { fit, getContentRect, type ContentRect, normalizedToPixel, pixelToNormalized } from './geometry';

export interface CanvasDimensions {
  width: number;
  height: number;
}

export interface ScaledBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Scale source frame coordinates [x1, y1, x2, y2] to display canvas dimensions,
 * preserving aspect ratio within contentRect (letterboxed/pillarboxed).
 */
export function scaleBox(
  box: [number, number, number, number],
  frameSize: [number, number],
  canvasSize: CanvasDimensions,
  contentRect?: ContentRect
): ScaledBox {
  const [fx, fy] = frameSize;
  const rect = contentRect || (fx > 0 && fy > 0 ? fit(canvasSize.width, canvasSize.height, fx, fy) : { x: 0, y: 0, width: canvasSize.width, height: canvasSize.height });

  if (fx <= 0 || fy <= 0 || rect.width <= 0 || rect.height <= 0) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }

  const sx = rect.width / fx;
  const sy = rect.height / fy;

  const [x1, y1, x2, y2] = box;
  const x = Math.max(0, rect.x + x1 * sx);
  const y = Math.max(0, rect.y + y1 * sy);
  const w = Math.max(0, (x2 - x1) * sx);
  const h = Math.max(0, (y2 - y1) * sy);

  return { x, y, w, h };
}

/**
 * Scale normalized point [0..1, 0..1] to display canvas coordinates relative to contentRect.
 */
export function scaleNormalizedPoint(
  point: [number, number],
  canvasSize: CanvasDimensions,
  contentRect?: ContentRect
): { x: number; y: number } {
  const rect = contentRect || { x: 0, y: 0, width: canvasSize.width, height: canvasSize.height };
  const [px, py] = point;
  return {
    x: rect.x + px * rect.width,
    y: rect.y + py * rect.height,
  };
}

/**
 * Draw zone boundary on the canvas with letterbox/pillarbox alignment.
 * - Special zones: dashed amber line, amber tint.
 * - Normal zones: dotted grey line, subtle grey tint.
 */
export function drawZone(
  ctx: CanvasRenderingContext2D,
  zone: Zone,
  canvasSize: CanvasDimensions,
  contentRect?: ContentRect
): void {
  if (!zone.points || zone.points.length < 2) return;

  ctx.save();

  const isSpecial = zone.kind === 'special';
  const strokeColor = isSpecial ? '#f59e0b' : '#9ca3af'; // amber-500 vs gray-400
  const fillColor = isSpecial ? 'rgba(245, 158, 11, 0.08)' : 'rgba(156, 163, 175, 0.04)';
  const dashPattern = isSpecial ? [6, 6] : [2, 4]; // dashed amber vs dotted grey

  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = isSpecial ? 2 : 1.5;
  ctx.setLineDash(dashPattern);
  ctx.fillStyle = fillColor;

  ctx.beginPath();
  const first = scaleNormalizedPoint(zone.points[0], canvasSize, contentRect);
  ctx.moveTo(first.x, first.y);

  for (let i = 1; i < zone.points.length; i++) {
    const pt = scaleNormalizedPoint(zone.points[i], canvasSize, contentRect);
    ctx.lineTo(pt.x, pt.y);
  }

  if (zone.shape === 'polygon') {
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  } else {
    // Line zone
    ctx.stroke();

    // Draw end nodes
    ctx.setLineDash([]);
    ctx.fillStyle = strokeColor;
    for (const p of zone.points) {
      const pt = scaleNormalizedPoint(p, canvasSize, contentRect);
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Direction indicator
    if (zone.direction && zone.points.length >= 2) {
      const p1 = scaleNormalizedPoint(zone.points[0], canvasSize, contentRect);
      const p2 = scaleNormalizedPoint(zone.points[1], canvasSize, contentRect);
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const len = Math.hypot(dx, dy) || 1;
      const nx = -dy / len;
      const ny = dx / len;

      ctx.beginPath();
      ctx.moveTo(midX, midY);
      const arrowLen = 14;
      ctx.lineTo(midX + nx * arrowLen, midY + ny * arrowLen);
      ctx.stroke();
    }
  }

  // Draw zone name label
  ctx.setLineDash([]);
  const labelPt = scaleNormalizedPoint(zone.points[0], canvasSize, contentRect);
  const text = `${zone.name} (${zone.kind})`;
  ctx.font = '11px sans-serif';
  const textWidth = ctx.measureText(text).width;

  ctx.fillStyle = 'rgba(17, 24, 39, 0.85)';
  ctx.fillRect(labelPt.x, labelPt.y - 18, textWidth + 8, 16);

  ctx.fillStyle = strokeColor;
  ctx.fillText(text, labelPt.x + 4, labelPt.y - 6);

  ctx.restore();
}

/**
 * Format attribute chip text from Track attributes.
 */
export function getAttributeChips(track: Track): string[] {
  const chips: string[] = [];

  if (track.attributes) {
    for (const [key, attr] of Object.entries(track.attributes)) {
      if (key === 'id_state' && attr.value === 'not_wearing') {
        chips.push('no ID?');
      } else if (attr.state === 'known') {
        chips.push(`${attr.value}`);
      } else if (key === 'plate') {
        chips.push('plate unknown');
      }
    }
  }

  return chips;
}

/**
 * Draw a single track detection box, track ID, and attribute chips on the canvas with letterbox/pillarbox alignment.
 */
export function drawTrack(
  ctx: CanvasRenderingContext2D,
  track: Track,
  frameSize: [number, number],
  canvasSize: CanvasDimensions,
  contentRect?: ContentRect
): void {
  const rect = contentRect || fit(canvasSize.width, canvasSize.height, frameSize[0], frameSize[1]);
  const box = scaleBox(track.bbox, frameSize, canvasSize, rect);
  if (box.w <= 0 || box.h <= 0) return;

  ctx.save();

  // Bounding box color
  const boxColor = '#3b82f6'; // blue-500
  ctx.strokeStyle = boxColor;
  ctx.lineWidth = 2;
  ctx.setLineDash([]);
  ctx.strokeRect(box.x, box.y, box.w, box.h);

  // Header pill with Track ID and class
  const headerText = `#${track.id} ${track.class}`;
  ctx.font = 'bold 11px sans-serif';
  const headerWidth = ctx.measureText(headerText).width;

  ctx.fillStyle = boxColor;
  ctx.fillRect(box.x, Math.max(0, box.y - 18), headerWidth + 8, 18);

  ctx.fillStyle = '#ffffff';
  ctx.fillText(headerText, box.x + 4, Math.max(13, box.y - 5));

  // Attribute chips below the bounding box
  const chips = getAttributeChips(track);
  if (chips.length > 0) {
    let chipX = box.x;
    const chipY = box.y + box.h + 4;
    ctx.font = '10px sans-serif';

    for (const chip of chips) {
      const chipWidth = ctx.measureText(chip).width;
      const isAlertChip = chip === 'no ID?' || chip.includes('critical');
      const chipBg = isAlertChip ? 'rgba(239, 68, 68, 0.9)' : 'rgba(31, 41, 55, 0.85)';
      const chipText = '#ffffff';

      ctx.fillStyle = chipBg;
      ctx.fillRect(chipX, chipY, chipWidth + 6, 14);

      ctx.fillStyle = chipText;
      ctx.fillText(chip, chipX + 3, chipY + 11);

      chipX += chipWidth + 10;
    }
  }

  ctx.restore();
}
