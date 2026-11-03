import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { CameraTile } from './CameraTile';
import type { Camera, TracksMessage } from '../../types';
import * as apiModule from '../../services/api';
import { wsService } from '../../services/websocket';

describe('CameraTile Component', () => {
  const mockCamera: Camera = {
    id: 'cam_02',
    name: 'South Exit',
    enabled: true,
    features: { vehicles: true, id_check: false },
    width: 1920,
    height: 1080,
    fps: 25,
    status: 'online',
  };

  let tracksCallback: ((msg: TracksMessage) => void) | null = null;
  let clearRectSpy: ReturnType<typeof vi.fn>;
  let strokeRectSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    tracksCallback = null;

    vi.spyOn(apiModule.api, 'listZones').mockResolvedValue([]);
    vi.spyOn(apiModule.api, 'getStreamInfo').mockResolvedValue({
      camera_id: 'cam_02',
      name: 'South Exit',
      status: 'online',
      webrtc_url: '',
      hls_url: '',
      width: 1920,
      height: 1080,
      fps: 25,
    });

    vi.spyOn(wsService, 'onTracks').mockImplementation((cb) => {
      tracksCallback = cb;
      return () => {
        tracksCallback = null;
      };
    });

    clearRectSpy = vi.fn();
    strokeRectSpy = vi.fn();

    // Mock HTMLCanvasElement 2D context
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      clearRect: clearRectSpy,
      strokeRect: strokeRectSpy,
      fillRect: vi.fn(),
      fillText: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      arc: vi.fn(),
      stroke: vi.fn(),
      fill: vi.fn(),
      closePath: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      setLineDash: vi.fn(),
      measureText: vi.fn().mockReturnValue({ width: 50 }),
      getBoundingClientRect: vi.fn().mockReturnValue({ width: 640, height: 360 }),
    }) as any;

    HTMLCanvasElement.prototype.getBoundingClientRect = vi.fn().mockReturnValue({
      width: 640,
      height: 360,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('clears overlay and does not draw tracks when camera status is offline', async () => {
    const offlineCamera: Camera = { ...mockCamera, status: 'offline' };
    await act(async () => {
      render(<CameraTile camera={offlineCamera} />);
    });

    expect(screen.getByText('Stream Unavailable')).toBeInTheDocument();
    expect(screen.getByText('Camera is currently marked offline.')).toBeInTheDocument();

    // Simulate tracks arriving for offline camera (should be ignored or cleared)
    if (tracksCallback) {
      act(() => {
        tracksCallback!({
          type: 'tracks',
          camera_id: 'cam_02',
          ts_ms: Date.now(),
          frame_size: [1920, 1080],
          tracks: [
            {
              id: 99,
              class: 'car',
              conf: 0.95,
              bbox: [100, 100, 300, 300],
              foot_point: [200, 300],
            },
          ],
        });
      });
    }

    // strokeRect for bounding box should NOT be called
    expect(strokeRectSpy).not.toHaveBeenCalled();
    expect(clearRectSpy).toHaveBeenCalled();
  });

  it('clears overlay when no tracks message arrives within timeout', async () => {
    await act(async () => {
      render(<CameraTile camera={mockCamera} />);
    });

    // Deliver a track message
    expect(tracksCallback).not.toBeNull();
    act(() => {
      tracksCallback!({
        type: 'tracks',
        camera_id: 'cam_02',
        ts_ms: Date.now(),
        frame_size: [1920, 1080],
        tracks: [
          {
            id: 1,
            class: 'car',
            conf: 0.92,
            bbox: [50, 50, 200, 200],
            foot_point: [125, 200],
          },
        ],
      });
    });

    // Box should be drawn
    expect(strokeRectSpy).toHaveBeenCalled();
    strokeRectSpy.mockClear();
    clearRectSpy.mockClear();

    // Advance timers by timeout (1000ms)
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    // Overlay must clear stale tracks
    expect(clearRectSpy).toHaveBeenCalled();
    expect(strokeRectSpy).not.toHaveBeenCalled();
  });

  it('shows connecting badge instead of LIVE when stream error occurs for online camera', async () => {
    // getStreamInfo rejects, causing streamError: true
    vi.spyOn(apiModule.api, 'getStreamInfo').mockRejectedValue(new Error('Connection failed'));

    await act(async () => {
      render(<CameraTile camera={mockCamera} />);
    });

    expect(screen.getByText('Stream Unavailable')).toBeInTheDocument();
    // Dot must NOT say LIVE when stream is unavailable
    expect(screen.queryByText('LIVE')).not.toBeInTheDocument();
    expect(screen.getByText('CONNECTING')).toBeInTheDocument();
  });
});
