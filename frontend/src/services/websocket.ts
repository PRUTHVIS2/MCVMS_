import type { Alert, CameraStatus, TracksMessage } from '../types';
import { api } from './api';

export type ConnectionState = 'connected' | 'connecting' | 'disconnected';

export interface CameraStatusMessage {
  type: 'camera.status';
  camera_id: string;
  status: CameraStatus;
  ts_ms?: number;
}

export interface AlertMessage {
  type: 'alert.created' | 'alert.updated';
  data: Alert;
}

export interface EventMessage {
  type: 'event.created' | 'event.updated' | 'event.ended';
  data: Record<string, unknown>;
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private state: ConnectionState = 'disconnected';
  private reconnectTimeout: number | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 20;
  private baseDelay = 1000;
  private maxDelay = 10000;
  private subscribedCameras = new Set<string>();

  private listeners: {
    tracks: Set<(msg: TracksMessage) => void>;
    cameraStatus: Set<(msg: CameraStatusMessage) => void>;
    alert: Set<(msg: AlertMessage) => void>;
    event: Set<(msg: EventMessage) => void>;
    connection: Set<(status: ConnectionState) => void>;
  } = {
    tracks: new Set(),
    cameraStatus: new Set(),
    alert: new Set(),
    event: new Set(),
    connection: new Set(),
  };

  public getState(): ConnectionState {
    return this.state;
  }

  private setState(newState: ConnectionState): void {
    if (this.state !== newState) {
      this.state = newState;
      this.listeners.connection.forEach((cb) => cb(newState));
    }
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.setState('connecting');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const token = api.getToken();
    const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : '';
    const wsUrl = `${protocol}//${host}/ws${tokenQuery}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.setState('connected');
        this.reconnectAttempts = 0;

        // Resubscribe to cameras if any
        if (this.subscribedCameras.size > 0) {
          this.send({
            type: 'subscribe',
            camera_ids: Array.from(this.subscribedCameras),
          });
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.dispatchMessage(data);
        } catch {
          // ignore non-json messages
        }
      };

      this.ws.onclose = () => {
        this.setState('disconnected');
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.setState('disconnected');
      };
    } catch {
      this.setState('disconnected');
      this.scheduleReconnect();
    }
  }

  public disconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }
    this.setState('disconnected');
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout) return;
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

    const delay = Math.min(
      this.baseDelay * Math.pow(1.5, this.reconnectAttempts),
      this.maxDelay
    );
    this.reconnectAttempts++;

    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, delay);
  }

  public send(payload: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  public subscribeCameras(cameraIds: string[]): void {
    cameraIds.forEach((id) => this.subscribedCameras.add(id));
    this.send({
      type: 'subscribe',
      camera_ids: cameraIds,
    });
  }

  public unsubscribeCameras(cameraIds: string[]): void {
    cameraIds.forEach((id) => this.subscribedCameras.delete(id));
    this.send({
      type: 'unsubscribe',
      camera_ids: cameraIds,
    });
  }

  private dispatchMessage(data: Record<string, unknown>): void {
    const type = data.type as string;

    if (type === 'tracks') {
      const msg = data as unknown as TracksMessage;
      this.listeners.tracks.forEach((cb) => cb(msg));
    } else if (type === 'camera.status') {
      const msg = data as unknown as CameraStatusMessage;
      this.listeners.cameraStatus.forEach((cb) => cb(msg));
    } else if (type === 'alert.created' || type === 'alert.updated') {
      const msg = data as unknown as AlertMessage;
      this.listeners.alert.forEach((cb) => cb(msg));
    } else if (type && (type.startsWith('event.'))) {
      const msg = data as unknown as EventMessage;
      this.listeners.event.forEach((cb) => cb(msg));
    }
  }

  // Event Listeners
  public onTracks(callback: (msg: TracksMessage) => void): () => void {
    this.listeners.tracks.add(callback);
    return () => this.listeners.tracks.delete(callback);
  }

  public onCameraStatus(callback: (msg: CameraStatusMessage) => void): () => void {
    this.listeners.cameraStatus.add(callback);
    return () => this.listeners.cameraStatus.delete(callback);
  }

  public onAlert(callback: (msg: AlertMessage) => void): () => void {
    this.listeners.alert.add(callback);
    return () => this.listeners.alert.delete(callback);
  }

  public onConnectionChange(callback: (status: ConnectionState) => void): () => void {
    this.listeners.connection.add(callback);
    return () => this.listeners.connection.delete(callback);
  }
}

export const wsService = new WebSocketService();
