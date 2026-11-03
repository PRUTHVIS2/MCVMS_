export type Role = 'owner' | 'admin' | 'incharge';

export interface User {
  id: string;
  username: string;
  role: Role;
  active: boolean;
  created_at: number;
  cameras: string[];
}

export type CameraStatus = 'online' | 'offline' | 'reconnecting' | 'disabled';

export interface CameraFeatures {
  vehicles: boolean;
  id_check: boolean;
}

export interface Camera {
  id: string;
  name: string;
  enabled: boolean;
  features: CameraFeatures;
  width: number | null;
  height: number | null;
  fps: number | null;
  status: CameraStatus;
}

export interface StreamInfo {
  camera_id: string;
  name: string;
  status: CameraStatus;
  webrtc_url: string;
  hls_url: string;
  width: number | null;
  height: number | null;
  fps: number | null;
}

export type ZoneKind = 'normal' | 'special';
export type ZoneShape = 'polygon' | 'line';
export type Direction = 'in' | 'out' | 'both';

export interface Zone {
  id: string;
  camera_id: string;
  name: string;
  kind: ZoneKind;
  shape: ZoneShape;
  points: [number, number][]; // normalized [0.0..1.0] coordinates
  direction?: Direction | null;
  is_read_area: boolean;
  enabled: boolean;
  created_at: number;
  updated_at: number;
}

export interface TrackAttribute {
  value: string | number | boolean;
  conf: number;
  state: 'known' | 'unknown';
}

export interface Track {
  id: number;
  class: string;
  conf: number;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2]
  foot_point: [number, number]; // [x, y]
  attributes?: Record<string, TrackAttribute>;
  in_zones?: string[];
}

export interface TracksMessage {
  type: 'tracks';
  camera_id: string;
  ts_ms: number;
  frame_ts_ms?: number;
  lag_ms?: number;
  frame_size: [number, number];
  tracks: Track[];
}

export type AlertSeverity = 'low' | 'medium' | 'critical';
export type AlertStatus = 'open' | 'acknowledged' | 'dismissed' | 'expired';

export interface Alert {
  id: string;
  camera_id: string;
  camera_name?: string;
  zone_name?: string;
  rule_id?: string;
  rule_name?: string;
  event_id?: string;
  level: AlertSeverity;
  message: string;
  status: AlertStatus;
  created_at: number;
  opened_at?: number;
  updated_at?: number;
  acked_at?: number;
  acked_by?: string;
}

