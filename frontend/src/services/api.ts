import type { Alert, Camera, StreamInfo, User, Zone } from '../types';

const TOKEN_KEY = 'mcvms_token';

class ApiClient {
  private baseUrl = '/api/v1';

  public getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  }

  public setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
  }

  public clearToken(): void {
    localStorage.removeItem(TOKEN_KEY);
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const token = this.getToken();
    const headers = new Headers(options.headers || {});

    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    if (!headers.has('Content-Type') && !(options.body instanceof FormData) && !(options.body instanceof URLSearchParams)) {
      headers.set('Content-Type', 'application/json');
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorMessage = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
        } else if (errorJson.error && errorJson.error.message) {
          errorMessage = errorJson.error.message;
        }
      } catch {
        // use default status message
      }
      throw new Error(errorMessage);
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // Auth
  public async login(username: string, password: string): Promise<{ access_token: string; token_type: string }> {
    const params = new URLSearchParams();
    params.append('username', username);
    params.append('password', password);

    const data = await this.request<{ access_token: string; token_type: string }>('/auth/login', {
      method: 'POST',
      body: params,
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    this.setToken(data.access_token);
    return data;
  }

  public async logout(): Promise<void> {
    try {
      await this.request('/auth/logout', { method: 'POST' });
    } finally {
      this.clearToken();
    }
  }

  public async getMe(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  // Cameras
  public async listCameras(): Promise<Camera[]> {
    return this.request<Camera[]>('/cameras');
  }

  public async getCamera(cameraId: string): Promise<Camera> {
    return this.request<Camera>(`/cameras/${cameraId}`);
  }

  public async getStreamInfo(cameraId: string): Promise<StreamInfo> {
    return this.request<StreamInfo>(`/cameras/${cameraId}/stream-info`);
  }

  public getSnapshotUrl(cameraId: string): string {
    return `${this.baseUrl}/cameras/${cameraId}/snapshot`;
  }

  // Zones
  public async listZones(cameraId: string): Promise<Zone[]> {
    return this.request<Zone[]>(`/cameras/${cameraId}/zones`);
  }

  // Alerts
  public async listAlerts(status = 'open'): Promise<Alert[]> {
    return this.request<Alert[]>(`/alerts?status=${encodeURIComponent(status)}`);
  }

  public async ackAlert(alertId: string, reason?: string): Promise<Alert> {
    return this.request<Alert>(`/alerts/${alertId}/ack`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || 'acknowledged via live wall' }),
    });
  }

  public async dismissAlert(alertId: string, reason: string): Promise<Alert> {
    return this.request<Alert>(`/alerts/${alertId}/dismiss`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }
}

export const api = new ApiClient();
