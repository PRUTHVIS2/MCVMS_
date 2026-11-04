import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AlertsPage } from './AlertsPage';
import type { Alert } from '../../types';
import * as apiModule from '../../services/api';
import * as AuthContext from '../../context/AuthContext';

describe('AlertsPage Component', () => {
  const mockAlerts: Alert[] = [
    {
      id: 'alert_01',
      camera_id: 'cam_01',
      camera_name: 'Main Gate',
      zone_name: 'Zone A',
      level: 'critical',
      message: 'Critical heavy vehicle detected in restricted zone',
      status: 'open',
      created_at: 1793768400000,
    },
    {
      id: 'alert_02',
      camera_id: 'cam_02',
      camera_name: 'South Exit',
      level: 'medium',
      message: 'South Exit offline since 10:30',
      status: 'open',
      created_at: 1793769000000,
    },
  ];

  beforeEach(() => {
    vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
      user: {
        id: 'u1',
        username: 'admin',
        role: 'admin',
        active: true,
        created_at: 1793760000000,
        cameras: [],
      },
      token: 'jwt',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      hasRole: vi.fn().mockReturnValue(true),
    });

    vi.spyOn(apiModule.api, 'listAlerts').mockResolvedValue(mockAlerts);
  });

  it('renders alerts table with severity badges and camera names', async () => {
    render(<AlertsPage />);

    await waitFor(() => {
      expect(screen.getByText('Critical heavy vehicle detected in restricted zone')).toBeInTheDocument();
      expect(screen.getByText('South Exit offline since 10:30')).toBeInTheDocument();
      expect(screen.getByText('Main Gate')).toBeInTheDocument();
    });
  });

  it('allows acknowledging an alert directly from the alerts list', async () => {
    const ackSpy = vi.spyOn(apiModule.api, 'ackAlert').mockResolvedValue({
      ...mockAlerts[0],
      status: 'acknowledged',
    });

    render(<AlertsPage />);

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Acknowledge' })[0]).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Acknowledge' })[0]);

    await waitFor(() => {
      expect(ackSpy).toHaveBeenCalledWith('alert_01');
    });
  });

  it('allows dismissing an alert with mandatory reason', async () => {
    const dismissSpy = vi.spyOn(apiModule.api, 'dismissAlert').mockResolvedValue({
      ...mockAlerts[0],
      status: 'dismissed',
    });

    render(<AlertsPage />);

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Dismiss' })[0]).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Dismiss' })[0]);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/maintenance/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/maintenance/i), {
      target: { value: 'Scheduled test delivery verified' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm Dismiss' }));

    await waitFor(() => {
      expect(dismissSpy).toHaveBeenCalledWith('alert_01', 'Scheduled test delivery verified');
    });
  });
});

