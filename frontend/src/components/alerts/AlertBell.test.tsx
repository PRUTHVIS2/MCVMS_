import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AlertBell } from './AlertBell';
import * as AlertsContext from '../../context/AlertsContext';
import { Alert } from '../../types';

describe('AlertBell Component', () => {
  const mockAckAlert = vi.fn();
  const mockToggleSound = vi.fn();
  const mockRefreshAlerts = vi.fn();

  const baseAlert: Alert = {
    id: 'alt_01',
    camera_id: 'cam01',
    camera_name: 'Main Gate',
    zone_name: 'Zone A',
    level: 'critical',
    message: 'Heavy vehicle in pedestrian zone',
    status: 'open',
    created_at: 1793673891000,
  };

  it('renders unacknowledged badge with critical pulse styling', () => {
    vi.spyOn(AlertsContext, 'useAlerts').mockReturnValue({
      alerts: [baseAlert],
      unackCount: 1,
      highestSeverity: 'critical',
      soundEnabled: true,
      toggleSound: mockToggleSound,
      ackAlert: mockAckAlert,
      refreshAlerts: mockRefreshAlerts,
    });

    render(<AlertBell />);

    const badge = screen.getByTestId('alert-bell-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('1');
    expect(badge.className).toContain('bg-red-600');
    expect(badge.className).toContain('animate-pulse');
  });

  it('renders medium severity badge with amber styling', () => {
    vi.spyOn(AlertsContext, 'useAlerts').mockReturnValue({
      alerts: [{ ...baseAlert, level: 'medium' }],
      unackCount: 3,
      highestSeverity: 'medium',
      soundEnabled: false,
      toggleSound: mockToggleSound,
      ackAlert: mockAckAlert,
      refreshAlerts: mockRefreshAlerts,
    });

    render(<AlertBell />);

    const badge = screen.getByTestId('alert-bell-badge');
    expect(badge).toHaveTextContent('3');
    expect(badge.className).toContain('bg-amber-500');
  });

  it('opens alert popover on click and allows acknowledging', () => {
    vi.spyOn(AlertsContext, 'useAlerts').mockReturnValue({
      alerts: [baseAlert],
      unackCount: 1,
      highestSeverity: 'critical',
      soundEnabled: true,
      toggleSound: mockToggleSound,
      ackAlert: mockAckAlert,
      refreshAlerts: mockRefreshAlerts,
    });

    render(<AlertBell />);

    const bellBtn = screen.getByLabelText('Alerts');
    fireEvent.click(bellBtn);

    // Popover is now visible
    expect(screen.getByText('System Alerts')).toBeInTheDocument();
    expect(screen.getByText('Heavy vehicle in pedestrian zone')).toBeInTheDocument();

    const ackBtn = screen.getByText('Acknowledge');
    fireEvent.click(ackBtn);
    expect(mockAckAlert).toHaveBeenCalledWith('alt_01');
  });

  it('toggles sound preference when sound button is clicked', () => {
    vi.spyOn(AlertsContext, 'useAlerts').mockReturnValue({
      alerts: [],
      unackCount: 0,
      highestSeverity: null,
      soundEnabled: true,
      toggleSound: mockToggleSound,
      ackAlert: mockAckAlert,
      refreshAlerts: mockRefreshAlerts,
    });

    render(<AlertBell />);

    const soundBtn = screen.getByLabelText('Toggle alert sound');
    fireEvent.click(soundBtn);
    expect(mockToggleSound).toHaveBeenCalled();
  });

  it('formats created_at in Asia/Kolkata timezone without showing Invalid Date', () => {
    const alertWithCreatedAt: Alert = {
      id: 'alt_02',
      camera_id: 'cam01',
      level: 'medium',
      message: 'Vehicle crossing detected',
      status: 'open',
      created_at: 1793673891000,
    };

    vi.spyOn(AlertsContext, 'useAlerts').mockReturnValue({
      alerts: [alertWithCreatedAt],
      unackCount: 1,
      highestSeverity: 'medium',
      soundEnabled: true,
      toggleSound: mockToggleSound,
      ackAlert: mockAckAlert,
      refreshAlerts: mockRefreshAlerts,
    });

    render(<AlertBell />);

    const bellBtn = screen.getByLabelText('Alerts');
    fireEvent.click(bellBtn);

    expect(screen.queryByText(/Invalid Date/i)).not.toBeInTheDocument();
    expect(screen.getByText('08:14:51')).toBeInTheDocument();
  });
});

