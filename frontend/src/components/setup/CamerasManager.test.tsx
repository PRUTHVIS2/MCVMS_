import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as CamerasContext from '../../context/CamerasContext';
import * as apiModule from '../../services/api';
import { CamerasManager } from './CamerasManager';

vi.mock('../../services/api', () => ({
  api: {
    createCamera: vi.fn(),
    updateCamera: vi.fn(),
    deleteCamera: vi.fn(),
    testCamera: vi.fn(),
  },
}));

describe('CamerasManager Component', () => {
  const mockRefreshCameras = vi.fn();
  const mockCameras = [
    {
      id: 'cam_01',
      name: 'Main Gate Entrance',
      enabled: true,
      features: { vehicles: true, id_check: false },
      width: 1920,
      height: 1080,
      fps: 25,
      status: 'online' as const,
    },
    {
      id: 'cam_02',
      name: 'Pedestrian Turnstile',
      enabled: false,
      features: { vehicles: false, id_check: true },
      width: null,
      height: null,
      fps: null,
      status: 'offline' as const,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();

    vi.spyOn(CamerasContext, 'useCameras').mockReturnValue({
      cameras: mockCameras,
      loading: false,
      refreshCameras: mockRefreshCameras,
      getCameraById: (id: string) => mockCameras.find((c) => c.id === id),
    });
  });

  it('renders list of cameras with their status, resolution, and feature badges', () => {
    render(<CamerasManager />);

    expect(screen.getByText('Camera Stream Management')).toBeInTheDocument();
    expect(screen.getByText('Main Gate Entrance')).toBeInTheDocument();
    expect(screen.getByText('Pedestrian Turnstile')).toBeInTheDocument();
    expect(screen.getByText(/1920×1080 @ 25fps/i)).toBeInTheDocument();
    expect(screen.getByText(/Unprobed \/ Offline/i)).toBeInTheDocument();
    expect(screen.getByText('✓ Vehicles / OCR')).toBeInTheDocument();
    expect(screen.getByText('✓ ID-Card Check')).toBeInTheDocument();
  });

  it('opens Add Camera modal and submits new camera', async () => {
    vi.spyOn(apiModule.api, 'createCamera').mockResolvedValue({
      id: 'cam_03',
      name: 'South Exit',
      enabled: true,
      features: { vehicles: true, id_check: false },
      width: null,
      height: null,
      fps: null,
      status: 'unknown' as const,
    });

    render(<CamerasManager />);

    // Click Add Camera
    fireEvent.click(screen.getByTestId('btn-add-camera'));
    expect(screen.getByText('Register New Camera Stream')).toBeInTheDocument();

    // Fill in fields
    fireEvent.change(screen.getByTestId('input-camera-name'), {
      target: { value: 'South Exit' },
    });
    fireEvent.change(screen.getByTestId('input-camera-rtsp'), {
      target: { value: 'rtsp://admin:pass@192.168.1.50:554/live' },
    });

    // Submit
    fireEvent.click(screen.getByTestId('btn-save-new-camera'));

    await waitFor(() => {
      expect(apiModule.api.createCamera).toHaveBeenCalledWith({
        name: 'South Exit',
        rtsp_url: 'rtsp://admin:pass@192.168.1.50:554/live',
        features: { vehicles: true, id_check: false },
      });
      expect(mockRefreshCameras).toHaveBeenCalled();
      expect(screen.getByTestId('cameras-message')).toHaveTextContent("Camera 'South Exit' registered successfully.");
    });
  });

  it('opens Edit Camera modal and updates camera name and rtsp', async () => {
    vi.spyOn(apiModule.api, 'updateCamera').mockResolvedValue({
      id: 'cam_01',
      name: 'Main Gate Entrance (Renamed)',
      enabled: true,
      features: { vehicles: true, id_check: true },
      width: 1920,
      height: 1080,
      fps: 25,
      status: 'online' as const,
    });

    render(<CamerasManager />);

    // Click Edit on cam_01
    fireEvent.click(screen.getByTestId('edit-camera-cam_01'));
    expect(screen.getByText('Edit Camera: Main Gate Entrance')).toBeInTheDocument();

    // Change name and enter new rtsp
    fireEvent.change(screen.getByTestId('edit-camera-name'), {
      target: { value: 'Main Gate Entrance (Renamed)' },
    });
    fireEvent.change(screen.getByTestId('edit-camera-rtsp'), {
      target: { value: 'rtsp://admin:newpass@192.168.1.10:554/stream2' },
    });

    // Save
    fireEvent.click(screen.getByTestId('btn-save-edit-camera'));

    await waitFor(() => {
      expect(apiModule.api.updateCamera).toHaveBeenCalledWith('cam_01', {
        name: 'Main Gate Entrance (Renamed)',
        enabled: true,
        features: { vehicles: true, id_check: false },
        rtsp_url: 'rtsp://admin:newpass@192.168.1.10:554/stream2',
      });
      expect(mockRefreshCameras).toHaveBeenCalled();
      expect(screen.getByTestId('cameras-message')).toHaveTextContent("Camera 'Main Gate Entrance (Renamed)' updated successfully.");
    });
  });

  it('tests stream connection and displays live feedback', async () => {
    vi.spyOn(apiModule.api, 'testCamera').mockResolvedValue({
      status: 'ok',
      width: 1920,
      height: 1080,
      fps: 30,
    });

    render(<CamerasManager />);

    fireEvent.click(screen.getByTestId('test-camera-cam_01'));

    await waitFor(() => {
      expect(apiModule.api.testCamera).toHaveBeenCalledWith('cam_01');
      expect(screen.getByText(/Live OK/i)).toBeInTheDocument();
      expect(screen.getByText(/1920×1080 @ 30fps/i)).toBeInTheDocument();
    });
  });

  it('handles stream connection test failure gracefully', async () => {
    vi.spyOn(apiModule.api, 'testCamera').mockResolvedValue({
      status: 'failed',
      reason: 'Could not open stream',
    });

    render(<CamerasManager />);

    fireEvent.click(screen.getByTestId('test-camera-cam_02'));

    await waitFor(() => {
      expect(apiModule.api.testCamera).toHaveBeenCalledWith('cam_02');
      expect(screen.getByText(/Test Failed:/i)).toBeInTheDocument();
      expect(screen.getByText('Could not open stream')).toBeInTheDocument();
    });
  });

  it('opens confirmation modal and deletes camera', async () => {
    vi.spyOn(apiModule.api, 'deleteCamera').mockResolvedValue({
      status: 'deleted',
      id: 'cam_01',
    });

    render(<CamerasManager />);

    // Click Delete
    fireEvent.click(screen.getByTestId('delete-camera-cam_01'));
    expect(screen.getByText("Delete Camera 'Main Gate Entrance'?")).toBeInTheDocument();
    expect(screen.getByText(/Warning: Deleting this camera will cascade-delete all defined zones/i)).toBeInTheDocument();

    // Confirm deletion
    fireEvent.click(screen.getByTestId('confirm-delete-camera'));

    await waitFor(() => {
      expect(apiModule.api.deleteCamera).toHaveBeenCalledWith('cam_01');
      expect(mockRefreshCameras).toHaveBeenCalled();
      expect(screen.getByTestId('cameras-message')).toHaveTextContent("Camera 'Main Gate Entrance' deleted.");
    });
  });
});
