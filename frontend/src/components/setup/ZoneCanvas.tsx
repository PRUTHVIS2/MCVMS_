import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { Direction, Zone, ZoneKind, ZoneShape } from '../../types';
import {
  findClosestVertex,
  fit,
  getLineDirectionArrow,
  pixelToNormalized,
  toCanvasCoords,
} from '../../utils/geometry';

interface ZoneCanvasProps {
  snapshotUrl?: string;
  shape: ZoneShape;
  kind: ZoneKind;
  direction?: Direction | null;
  existingZones?: Zone[];
  points: [number, number][];
  onPointsChange: (points: [number, number][]) => void;
  disabled?: boolean;
  frameWidth?: number;
  frameHeight?: number;
}

export const ZoneCanvas: React.FC<ZoneCanvasProps> = ({
  snapshotUrl,
  shape,
  kind,
  direction = 'in',
  existingZones = [],
  points,
  onPointsChange,
  disabled = false,
  frameWidth,
  frameHeight,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  const [dimensions, setDimensions] = useState<{ width: number; height: number }>({ width: 800, height: 450 });
  const [imageSize, setImageSize] = useState<{ width: number; height: number }>({
    width: frameWidth || 1920,
    height: frameHeight || 1080,
  });
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const [imageError, setImageError] = useState(false);

  // Sync prop changes for frame dimensions
  useEffect(() => {
    if (frameWidth && frameHeight && frameWidth > 0 && frameHeight > 0) {
      setImageSize({ width: frameWidth, height: frameHeight });
    }
  }, [frameWidth, frameHeight]);

  // Read natural image dimensions when snapshot loads
  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    if (img.naturalWidth > 0 && img.naturalHeight > 0) {
      setImageSize({ width: img.naturalWidth, height: img.naturalHeight });
    }
  };

  // Resize canvas when container size changes
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        const width = Math.floor(rect.width);
        const height = Math.max(360, Math.floor(rect.width * (9 / 16)));
        if (width > 0 && height > 0) {
          setDimensions({ width, height });
        }
      }
    };

    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  // Compute shared letterbox contentRect
  const contentRect = fit(dimensions.width, dimensions.height, imageSize.width, imageSize.height);

  // Redraw canvas
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = dimensions;
    ctx.clearRect(0, 0, width, height);

    // 1. Draw existing zones (inactive background)
    existingZones.forEach((z) => {
      if (!z.points || z.points.length < 2) return;
      const pts = z.points.map((p) => toCanvasCoords(p, contentRect));

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) {
        ctx.lineTo(pts[i][0], pts[i][1]);
      }
      if (z.shape === 'polygon') {
        ctx.closePath();
        ctx.fillStyle = z.kind === 'special' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(59, 130, 246, 0.12)';
        ctx.fill();
        ctx.strokeStyle = z.kind === 'special' ? 'rgba(245, 158, 11, 0.6)' : 'rgba(59, 130, 246, 0.6)';
      } else {
        ctx.strokeStyle = z.kind === 'special' ? 'rgba(245, 158, 11, 0.7)' : 'rgba(59, 130, 246, 0.7)';
      }
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.stroke();

      // Zone name tag
      ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
      ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
      const tagText = `${z.name} (${z.kind})`;
      const textWidth = ctx.measureText(tagText).width;
      ctx.fillRect(pts[0][0] + 4, pts[0][1] - 16, textWidth + 8, 16);
      ctx.fillStyle = z.kind === 'special' ? '#f59e0b' : '#60a5fa';
      ctx.fillText(tagText, pts[0][0] + 8, pts[0][1] - 4);

      ctx.restore();
    });

    // 2. Draw current active zone being edited
    if (points.length > 0) {
      const activePts = points.map((p) => toCanvasCoords(p, contentRect));
      const strokeColor = kind === 'special' ? '#f59e0b' : '#3b82f6';
      const fillColor = kind === 'special' ? 'rgba(245, 158, 11, 0.28)' : 'rgba(59, 130, 246, 0.22)';

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(activePts[0][0], activePts[0][1]);
      for (let i = 1; i < activePts.length; i++) {
        ctx.lineTo(activePts[i][0], activePts[i][1]);
      }

      if (shape === 'polygon' && activePts.length >= 3) {
        ctx.closePath();
        ctx.fillStyle = fillColor;
        ctx.fill();
      }

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.5;
      ctx.setLineDash([]);
      ctx.stroke();

      // For line shape, draw directional arrow
      if (shape === 'line' && points.length === 2) {
        const arrow = getLineDirectionArrow(points[0], points[1], direction, contentRect);
        if (arrow) {
          ctx.beginPath();
          ctx.moveTo(arrow.start[0], arrow.start[1]);
          ctx.lineTo(arrow.end[0], arrow.end[1]);
          ctx.strokeStyle = '#ef4444'; // Red arrow for crossing direction
          ctx.lineWidth = 2;
          ctx.stroke();

          // Arrowhead
          const angle = Math.atan2(arrow.end[1] - arrow.start[1], arrow.end[0] - arrow.start[0]);
          const headlen = 8;
          ctx.beginPath();
          ctx.moveTo(arrow.end[0], arrow.end[1]);
          ctx.lineTo(
            arrow.end[0] - headlen * Math.cos(angle - Math.PI / 6),
            arrow.end[1] - headlen * Math.sin(angle - Math.PI / 6)
          );
          ctx.moveTo(arrow.end[0], arrow.end[1]);
          ctx.lineTo(
            arrow.end[0] - headlen * Math.cos(angle + Math.PI / 6),
            arrow.end[1] - headlen * Math.sin(angle + Math.PI / 6)
          );
          ctx.stroke();
        }
      }

      // Draw drag handles / vertices
      activePts.forEach((pt, idx) => {
        const isHovered = hoveredIdx === idx;
        const isDragging = draggingIdx === idx;

        ctx.beginPath();
        ctx.arc(pt[0], pt[1], isDragging ? 7 : isHovered ? 6 : 4.5, 0, Math.PI * 2);
        ctx.fillStyle = isDragging ? '#ffffff' : isHovered ? '#fbbf24' : strokeColor;
        ctx.fill();
        ctx.strokeStyle = '#0f172a';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Vertex index label
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px sans-serif';
        ctx.fillText(String(idx + 1), pt[0] + 8, pt[1] - 8);
      });

      ctx.restore();
    }
  }, [dimensions, contentRect, existingZones, points, shape, kind, direction, hoveredIdx, draggingIdx]);

  useEffect(() => {
    draw();
  }, [draw]);

  // Pointer event handlers for drawing and dragging
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (disabled) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Check if clicked on existing vertex for dragging
    const hitIdx = findClosestVertex(points, [clickX, clickY], contentRect, undefined, 14);
    if (hitIdx !== -1) {
      setDraggingIdx(hitIdx);
      return;
    }

    // Ignore clicks outside the displayed contentRect (i.e. in letterbox bars)
    const isInside =
      clickX >= contentRect.x &&
      clickX <= contentRect.x + contentRect.width &&
      clickY >= contentRect.y &&
      clickY <= contentRect.y + contentRect.height;

    if (!isInside) {
      return;
    }

    const newPt = pixelToNormalized(clickX, clickY, contentRect);

    if (shape === 'line' && points.length >= 2) {
      // Line is already complete, reset to start new line
      onPointsChange([newPt]);
      return;
    }

    onPointsChange([...points, newPt]);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (disabled) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    if (draggingIdx !== null) {
      const updated = [...points];
      updated[draggingIdx] = pixelToNormalized(mouseX, mouseY, contentRect);
      onPointsChange(updated);
    } else {
      const hitIdx = findClosestVertex(points, [mouseX, mouseY], contentRect, undefined, 14);
      setHoveredIdx(hitIdx !== -1 ? hitIdx : null);
    }
  };

  const handleMouseUp = () => {
    setDraggingIdx(null);
  };

  return (
    <div
      ref={containerRef}
      className="relative w-full rounded-xl overflow-hidden bg-slate-900 border border-slate-800 shadow-inner select-none flex items-center justify-center"
      style={{ height: dimensions.height }}
      data-testid="zone-canvas-container"
    >
      {/* Background Camera Snapshot with object-contain */}
      {snapshotUrl && !imageError ? (
        <img
          ref={imgRef}
          src={snapshotUrl}
          alt="Live camera snapshot"
          className="absolute inset-0 w-full h-full object-contain pointer-events-none select-none"
          onLoad={handleImageLoad}
          onError={() => setImageError(true)}
        />
      ) : (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-950 text-slate-600">
          <svg className="w-12 h-12 mb-2 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <span className="text-xs font-mono tracking-wider">CAMERA SNAPSHOT PREVIEW (CANVAS READY)</span>
        </div>
      )}

      {/* Grid overlay for positioning reference (clipped to contentRect) */}
      <div
        className="absolute pointer-events-none opacity-15 border border-slate-700/40"
        style={{
          left: contentRect.x,
          top: contentRect.y,
          width: contentRect.width,
          height: contentRect.height,
          backgroundImage:
            'linear-gradient(to right, #475569 1px, transparent 1px), linear-gradient(to bottom, #475569 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      {/* Drawing Canvas */}
      <canvas
        ref={canvasRef}
        width={dimensions.width}
        height={dimensions.height}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className={`absolute inset-0 w-full h-full ${
          draggingIdx !== null ? 'cursor-grabbing' : hoveredIdx !== null ? 'cursor-grab' : 'cursor-crosshair'
        }`}
        data-testid="zone-canvas"
      />

      {/* Canvas Status & Helper Pill */}
      <div className="absolute top-3 left-3 flex items-center space-x-2 pointer-events-none">
        <span
          className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border shadow-sm ${
            kind === 'special'
              ? 'bg-amber-500/90 text-slate-950 border-amber-400'
              : 'bg-blue-600/90 text-white border-blue-500'
          }`}
        >
          {kind} Zone ({shape})
        </span>
        <span className="text-[10px] bg-slate-900/80 text-slate-300 px-2 py-0.5 rounded font-mono border border-slate-700/60">
          {points.length} {points.length === 1 ? 'vertex' : 'vertices'}
        </span>
        <span className="text-[10px] bg-slate-900/80 text-slate-400 px-2 py-0.5 rounded font-mono border border-slate-700/60">
          {imageSize.width}x{imageSize.height}
        </span>
      </div>
    </div>
  );
};
