import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { UsersAuditPage } from './UsersAuditPage';
import * as apiModule from '../../services/api';

vi.mock('../../services/api', () => ({
  api: {
    listUsers: vi.fn(),
    createUser: vi.fn(),
    listAuditLogs: vi.fn(),
  },
}));

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', username: 'admin', role: 'owner' },
  }),
}));

describe('UsersAuditPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.spyOn(apiModule.api, 'listUsers').mockResolvedValue([
      { id: 'u1', username: 'admin', role: 'owner', active: true, cameras: [], created_at: 1793769000000 },
      { id: 'u2', username: 'guard1', role: 'guard', active: true, cameras: ['cam_01'], created_at: 1793769000000 },
    ]);

    vi.spyOn(apiModule.api, 'listAuditLogs').mockResolvedValue([
      {
        id: 1,
        ts: 1793769000000,
        user_id: 'u1',
        username: 'admin',
        action: 'user.login',
        target: 'auth',
        detail: { ip: '127.0.0.1' },
      },
    ]);
  });

  it('renders user management table for owner', async () => {
    render(<UsersAuditPage />);

    await waitFor(() => {
      expect(screen.getByText('User Management')).toBeInTheDocument();
      expect(screen.getByText('admin')).toBeInTheDocument();
      expect(screen.getByText('guard1')).toBeInTheDocument();
      expect(screen.getByText('Add New User')).toBeInTheDocument();
    });
  });

  it('switches to audit trail tab and displays audit entries', async () => {
    render(<UsersAuditPage />);

    await waitFor(() => {
      expect(screen.getByText('Audit Log Feed')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Audit Log Feed'));

    await waitFor(() => {
      expect(screen.getByText('user.login')).toBeInTheDocument();
      expect(screen.getByText(/127\.0\.0\.1/)).toBeInTheDocument();
    });
  });
});
