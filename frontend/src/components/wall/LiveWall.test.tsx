import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { LiveWall } from './LiveWall';
import * as CamerasContext from '../../context/CamerasContext';
import { Camera } from '../../types';

describe('LiveWall Component', () => {
  const mockRefreshCameras = vi.fn();

  const mockCameras: Camera[] = [
    {
      id: 'cam_01',
      name: 'North Gate',
      enabled: true,
      features: { vehicles: true, id_check: false },
      width: 1920,
      height: 1080,
      fps: 30,
      status: 'online',
    },
    {
      id: 'cam_02',
      name: 'South Exit',
      enabled: true,
      features: { vehicles: true, id_check: true },
      width: 1920,
      height: 1080,
      fps: 25,
      status: 'offline',
    },
  ];

  it('renders camera grid with online and offline status counters', () => {
    vi.spyOn(CamerasContext, 'useCameras').mockReturnValue({
      cameras: mockCameras,
      loading: false,
      refreshCameras: mockRefreshCameras,
      getCameraById: (id: string) => mockCameras.find((c) => c.id === id),
    });

    render(<LiveWall />);

    expect(screen.getByText('2 Cameras')).toBeInTheDocument();
    expect(screen.getByText('1 Online')).toBeInTheDocument();
    expect(screen.getByText('1 Offline')).toBeInTheDocument();
    expect(screen.getByText('North Gate')).toBeInTheDocument();
    expect(screen.getByText('South Exit')).toBeInTheDocument();
  });

  it('displays empty state when no cameras are registered', () => {
    vi.spyOn(CamerasContext, 'useCameras').mockReturnValue({
      cameras: [],
      loading: false,
      refreshCameras: mockRefreshCameras,
      getCameraById: () => undefined,
    });

    render(<LiveWall />);

    expect(screen.getByText('No Cameras Configured')).toBeInTheDocument();
  });

  it('allows focusing on a single camera tile', () => {
    vi.spyOn(CamerasContext, 'useCameras').mockReturnValue({
      cameras: mockCameras,
      loading: false,
      refreshCameras: mockRefreshCameras,
      getCameraById: (id: string) => mockCameras.find((c) => c.id === id),
    });

    render(<LiveWall />);

    const focusButtons = screen.getAllByLabelText('Focus camera');
    expect(focusButtons.length).toBe(2);

    // Focus on first camera
    fireEvent.click(focusButtons[0]);
    expect(screen.getByText('Back to Wall')).toBeInTheDocument();

    // North Gate is visible, South Exit is hidden
    expect(screen.getByText('North Gate')).toBeInTheDocument();
    expect(screen.queryByText('South Exit')).not.toBeInTheDocument();

    // Click Back to Wall
    fireEvent.click(screen.getByText('Back to Wall'));
    expect(screen.getByText('South Exit')).toBeInTheDocument();
  });
});

