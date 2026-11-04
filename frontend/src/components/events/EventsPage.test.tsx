import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EventsPage } from './EventsPage';
import type { EventItem } from '../../types';
import * as apiModule from '../../services/api';
import * as CamerasContext from '../../context/CamerasContext';

describe('EventsPage Component', () => {
  const mockEvents: EventItem[] = [
    {
      id: 'event_01',
      camera_id: 'cam_01',
      camera_name: 'Main Gate Entrance',
      zone_name: 'Loading Zone',
      severity: 'critical',
      kind: 'heavy_vehicle',
      status: 'open',
      started_at: 1793768400000, // 10:30:00 IST
      clip_id: 'clip_01',
      confidence: 0.94,
      subject: { category: 'truck', colour: 'white', plate: 'KA05AB1234' },
    },
    {
      id: 'event_02',
      camera_id: 'cam_02',
      camera_name: 'South Exit',
      zone_name: 'Exit Line',
      severity: 'medium',
      kind: 'line_crossing',
      status: 'acknowledged',
      started_at: 1793769400000,
      clip_id: 'clip_02',
      confidence: 0.88,
      subject: { category: 'car' },
    },
  ];

  beforeEach(() => {
    vi.spyOn(CamerasContext, 'useCameras').mockReturnValue({
      cameras: [
        {
          id: 'cam_01',
          name: 'Main Gate Entrance',
          enabled: true,
          features: { vehicles: true, id_check: false },
          width: 1920,
          height: 1080,
          fps: 25,
          status: 'online',
        },
      ],
      loading: false,
      refreshCameras: vi.fn(),
      getCameraById: vi.fn(),
    });

    vi.spyOn(apiModule.api, 'listEvents').mockResolvedValue(mockEvents);
    vi.spyOn(apiModule.api, 'getEventClipUrl').mockReturnValue('/api/v1/events/event_01/clip');
    vi.spyOn(apiModule.api, 'getEventKeyframeUrl').mockImplementation(
      (id, label) => `/api/v1/events/${id}/keyframes/${label}`
    );
  });

  it('renders events list with IST timestamps, severity, and camera names', async () => {
    render(<EventsPage />);

    await waitFor(() => {
      expect(screen.getByText(/heavy vehicle/i)).toBeInTheDocument();
      expect(screen.getByText(/line crossing/i)).toBeInTheDocument();
      expect(screen.getAllByText('Main Gate Entrance').length).toBeGreaterThan(0);
      expect(screen.getByText('critical')).toBeInTheDocument();
    });
  });

  it('opens detail drawer with clip player and trigger point indicator on event click', async () => {
    render(<EventsPage />);

    await waitFor(() => {
      expect(screen.getByText(/heavy vehicle/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('event-row-event_01'));

    await waitFor(() => {
      expect(screen.getByTestId('event-detail-drawer')).toBeInTheDocument();
      expect(screen.getByTestId('event-clip-player')).toBeInTheDocument();
      expect(screen.getByText(/Trigger Point: 15s/i)).toBeInTheDocument();
      expect(screen.getByText('KA05AB1234')).toBeInTheDocument();
    });
  });

  it('allows acknowledging an event from detail drawer', async () => {
    const ackSpy = vi.spyOn(apiModule.api, 'ackEvent').mockResolvedValue({
      ...mockEvents[0],
      status: 'acknowledged',
    });

    render(<EventsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('event-row-event_01')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('event-row-event_01'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Acknowledge' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }));

    await waitFor(() => {
      expect(ackSpy).toHaveBeenCalledWith('event_01');
    });
  });

  it('allows marking an event as a false alarm with required reason', async () => {
    const falseAlarmSpy = vi.spyOn(apiModule.api, 'markFalseAlarm').mockResolvedValue({
      ...mockEvents[0],
      status: 'false_alarm',
    });

    render(<EventsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('event-row-event_01')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('event-row-event_01'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Mark False Alarm' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mark False Alarm' }));

    // Modal dialog opens
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/camera reflection/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/camera reflection/i), {
      target: { value: 'Shadow of tree triggered false positive' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm False Alarm' }));

    await waitFor(() => {
      expect(falseAlarmSpy).toHaveBeenCalledWith('event_01', 'Shadow of tree triggered false positive');
    });
  });
});
