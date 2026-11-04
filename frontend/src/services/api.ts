import type {
  ActionItem,
  Alert,
  AuditLogEntry,
  CalendarExemption,
  Camera,
  CameraFeatures,
  Direction,
  DryRunResponse,
  EventItem,
  RegisteredActionSpec,
  RulePresetsResponse,
  SampleClip,
  StreamInfo,
  SystemHealth,
  User,
  Zone,
  ZoneKind,
  ZoneShape,
} from '../types';

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

  public async createCamera(data: {
    name: string;
    rtsp_url: string;
    features?: CameraFeatures;
  }): Promise<Camera> {
    return this.request<Camera>('/cameras', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async updateCamera(
    cameraId: string,
    update: { name?: string; enabled?: boolean; features?: CameraFeatures; rtsp_url?: string }
  ): Promise<Camera> {
    return this.request<Camera>(`/cameras/${cameraId}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
  }

  public async deleteCamera(cameraId: string): Promise<{ status: string; id: string }> {
    return this.request<{ status: string; id: string }>(`/cameras/${cameraId}`, {
      method: 'DELETE',
    });
  }

  public async testCamera(cameraId: string): Promise<{
    status: string;
    width?: number;
    height?: number;
    fps?: number;
    reason?: string;
  }> {
    return this.request<{
      status: string;
      width?: number;
      height?: number;
      fps?: number;
      reason?: string;
    }>(`/cameras/${cameraId}/test`, {
      method: 'POST',
    });
  }

  // Zones
  public async listZones(cameraId: string): Promise<Zone[]> {
    return this.request<Zone[]>(`/cameras/${cameraId}/zones`);
  }

  public async getZone(zoneId: string): Promise<Zone> {
    return this.request<Zone>(`/zones/${zoneId}`);
  }

  public async createZone(
    cameraId: string,
    zone: {
      name: string;
      kind: ZoneKind;
      shape: ZoneShape;
      points: [number, number][];
      direction?: Direction | null;
      is_read_area?: boolean;
      enabled?: boolean;
    }
  ): Promise<Zone> {
    return this.request<Zone>(`/cameras/${cameraId}/zones`, {
      method: 'POST',
      body: JSON.stringify(zone),
    });
  }

  public async updateZone(
    zoneId: string,
    update: {
      name?: string;
      kind?: ZoneKind;
      shape?: ZoneShape;
      points?: [number, number][];
      direction?: Direction | null;
      is_read_area?: boolean;
      enabled?: boolean;
    }
  ): Promise<Zone> {
    return this.request<Zone>(`/zones/${zoneId}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
  }

  public async deleteZone(zoneId: string): Promise<{ status: string; id: string }> {
    return this.request<{ status: string; id: string }>(`/zones/${zoneId}`, {
      method: 'DELETE',
    });
  }

  // Actions & Rules
  public async listActions(zoneId: string): Promise<ActionItem[]> {
    return this.request<ActionItem[]>(`/zones/${zoneId}/actions`);
  }

  public async getAction(actionId: string): Promise<ActionItem> {
    return this.request<ActionItem>(`/actions/${actionId}`);
  }

  public async createAction(zoneId: string, spec: RegisteredActionSpec): Promise<ActionItem> {
    return this.request<ActionItem>(`/zones/${zoneId}/actions`, {
      method: 'POST',
      body: JSON.stringify(spec),
    });
  }

  public async updateAction(
    actionId: string,
    update: { name?: string; enabled?: boolean; spec?: RegisteredActionSpec }
  ): Promise<ActionItem> {
    return this.request<ActionItem>(`/actions/${actionId}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
  }

  public async deleteAction(actionId: string): Promise<{ status: string; id: string }> {
    return this.request<{ status: string; id: string }>(`/actions/${actionId}`, {
      method: 'DELETE',
    });
  }

  // Templates & Presets
  public async getRuleTemplates(): Promise<RulePresetsResponse> {
    return this.request<RulePresetsResponse>('/rule-templates');
  }

  public async listSampleClips(): Promise<SampleClip[]> {
    return this.request<SampleClip[]>('/actions/sample-clips');
  }

  // Dry-run Simulation
  public async dryRunAction(
    actionId: string,
    params: { clip_id?: string; clip_path?: string; max_frames?: number }
  ): Promise<DryRunResponse> {
    return this.request<DryRunResponse>(`/actions/${actionId}/dry-run`, {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  public async dryRunDraft(params: {
    zone_id: string;
    spec: RegisteredActionSpec;
    clip_id?: string;
    clip_path?: string;
    max_frames?: number;
  }): Promise<DryRunResponse> {
    return this.request<DryRunResponse>('/actions/dry-run-draft', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  // Calendar Exemptions
  public async listCalendarExemptions(): Promise<CalendarExemption[]> {
    return this.request<CalendarExemption[]>('/calendar');
  }

  public async createCalendarExemption(data: {
    label: string;
    date_from: string;
    date_to: string;
    scope: 'all' | 'camera' | 'action';
    camera_id?: string | null;
    action_id?: string | null;
  }): Promise<CalendarExemption> {
    return this.request<CalendarExemption>('/calendar', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async deleteCalendarExemption(exemptionId: string): Promise<{ status: string; id: string }> {
    return this.request<{ status: string; id: string }>(`/calendar/${exemptionId}`, {
      method: 'DELETE',
    });
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

  // Events
  public async listEvents(filters?: {
    camera_id?: string;
    severity?: string;
    status?: string;
    limit?: number;
  }): Promise<EventItem[]> {
    const params = new URLSearchParams();
    if (filters?.camera_id) params.append('camera_id', filters.camera_id);
    if (filters?.severity) params.append('severity', filters.severity);
    if (filters?.status) params.append('status', filters.status);
    if (filters?.limit) params.append('limit', String(filters.limit));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this.request<EventItem[]>(`/events${qs}`);
  }

  public async getEvent(eventId: string): Promise<EventItem> {
    return this.request<EventItem>(`/events/${eventId}`);
  }

  public async ackEvent(eventId: string): Promise<EventItem> {
    return this.request<EventItem>(`/events/${eventId}/ack`, { method: 'POST' });
  }

  public async markFalseAlarm(eventId: string, reason: string): Promise<EventItem> {
    return this.request<EventItem>(`/events/${eventId}/false-alarm`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  public getEventClipUrl(eventId: string): string {
    const token = this.getToken();
    return `${this.baseUrl}/events/${eventId}/clip${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  }

  public getEventKeyframeUrl(eventId: string, label: string): string {
    const token = this.getToken();
    return `${this.baseUrl}/events/${eventId}/keyframes/${label}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  }

  // System & Health
  public async getSystemHealth(): Promise<SystemHealth> {
    return this.request<SystemHealth>('/system/health');
  }

  public async getSystemConfigSummary(): Promise<any> {
    return this.request<any>('/system/config-summary');
  }

  public async listAuditLogs(filters?: { action?: string; limit?: number }): Promise<AuditLogEntry[]> {
    const params = new URLSearchParams();
    if (filters?.action) params.append('action', filters.action);
    if (filters?.limit) params.append('limit', String(filters.limit));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this.request<AuditLogEntry[]>(`/audit${qs}`);
  }

  // Users (owner)
  public async listUsers(): Promise<User[]> {
    return this.request<User[]>('/users');
  }

  public async createUser(user: { username: string; password: string; role: string }): Promise<User> {
    return this.request<User>('/users', {
      method: 'POST',
      body: JSON.stringify(user),
    });
  }
}

export const api = new ApiClient();
