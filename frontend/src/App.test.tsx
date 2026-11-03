import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import App from './App';
import * as AuthContext from './context/AuthContext';
import { User } from './types';

describe('App Component', () => {
  it('renders login page when user is not authenticated', () => {
    vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
      user: null,
      token: null,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      hasRole: vi.fn().mockReturnValue(false),
    });

    render(<App />);
    expect(screen.getByRole('heading', { name: /MCVMS/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sign In/i })).toBeInTheDocument();
  });

  it('renders shell and live wall when user is authenticated', () => {
    const mockUser: User = {
      id: 'usr_01',
      username: 'admin',
      role: 'owner',
      active: true,
      created_at: 1793673891000,
      cameras: [],
    };

    vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
      user: mockUser,
      token: 'valid_jwt_token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      hasRole: vi.fn().mockReturnValue(true),
    });

    render(<App />);
    expect(screen.getByText('Live Wall')).toBeInTheDocument();
    expect(screen.getByText('admin')).toBeInTheDocument();
    expect(screen.getByText('owner')).toBeInTheDocument();
  });
});
