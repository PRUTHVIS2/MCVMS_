import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { LoginPage } from './LoginPage';
import * as AuthContext from '../../context/AuthContext';

describe('LoginPage Component', () => {
  it('displays generic error message when login fails due to incorrect password', async () => {
    const mockLogin = vi.fn().mockRejectedValue(new Error('Incorrect username or password'));

    vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
      user: null,
      token: null,
      isLoading: false,
      login: mockLogin,
      logout: vi.fn(),
      hasRole: vi.fn().mockReturnValue(false),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByPlaceholderText('admin'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'wrongpass' } });
    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

    await waitFor(() => {
      expect(screen.getByTestId('login-error-alert')).toBeInTheDocument();
      expect(screen.getByText('Incorrect username or password')).toBeInTheDocument();
    });
  });

  it('displays generic error message without enumerating user when user does not exist', async () => {
    const mockLogin = vi.fn().mockRejectedValue(new Error('Incorrect username or password'));

    vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
      user: null,
      token: null,
      isLoading: false,
      login: mockLogin,
      logout: vi.fn(),
      hasRole: vi.fn().mockReturnValue(false),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByPlaceholderText('admin'), { target: { value: 'unknown_user' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'password123' } });
    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

    await waitFor(() => {
      expect(screen.getByTestId('login-error-alert')).toBeInTheDocument();
      expect(screen.getByText('Incorrect username or password')).toBeInTheDocument();
    });
  });
});

