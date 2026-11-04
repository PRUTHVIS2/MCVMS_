import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SystemPage } from './SystemPage';
import * as apiModule from '../../services/api';

vi.mock('../../services/api', () => ({
  api: {
    getSystemHealth: vi.fn(),
    getSystemConfigSummary: vi.fn(),
  },
}));

describe('SystemPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.spyOn(apiModule.api, 'getSystemHealth').mockResolvedValue({
      status: 'healthy',
      timestamp: 1793769000000,
      disk: {
        total_gb: 500,
        used_gb: 120,
        free_gb: 380,
        percent_used: 24,
        status: 'ok',
      },
      gpu: {
        available: true,
        device: 'cuda',
        name: 'NVIDIA GeForce RTX 3080',
        memory_used_mb: 2150,
        memory_total_mb: 10240,
      },
      cameras: [
        {
          id: 'cam_01',
          name: 'Main Gate Entrance',
          fps: 15.0,
          status: 'online',
          enabled: true,
          rtsp_url_enc: 'rtsp://test',
          features_json: '{}',
          created_at: 1793769000000,
          updated_at: 1793769000000,
        },
      ],
      decode_errors: { cam_01: 2 },
    });

    vi.spyOn(apiModule.api, 'getSystemConfigSummary').mockResolvedValue({
      app: { timezone: 'Asia/Kolkata', mode: 'live', device: 'cuda' },
      model: { weights: 'yolo11n.pt', tracker: 'bytetrack.yaml' },
      heavy_categories: ['truck', 'bus'],
      clips: { retry_limit: 5, retry_interval_s: 5.0, segment_gap_tolerance_ms: 2500 },
      retention: { video_days: 7 },
    });
  });

  it('renders system health metrics, storage, and worker status', async () => {
    render(<SystemPage />);

    await waitFor(() => {
      expect(screen.getByText('System Health & Metrics')).toBeInTheDocument();
      expect(screen.getByText('NVIDIA GeForce RTX 3080')).toBeInTheDocument();
      expect(screen.getByText('Main Gate Entrance')).toBeInTheDocument();
      expect(screen.getByText('yolo11n.pt')).toBeInTheDocument();
    });
  });

  it('renders "About accuracy" limitations section from docs/01 s6', async () => {
    render(<SystemPage />);

    await waitFor(() => {
      expect(screen.getByTestId('about-accuracy-section')).toBeInTheDocument();
    });

    expect(screen.getByText(/1\. Licence Plates/i)).toBeInTheDocument();
    expect(screen.getByText(/2\. Vehicle Colour/i)).toBeInTheDocument();
    expect(screen.getByText(/3\. Heavy Vehicle Heuristic/i)).toBeInTheDocument();
    expect(screen.getByText(/4\. ID-Card Physical Visibility/i)).toBeInTheDocument();
    expect(screen.getByText(/5\. No Identity Guessing/i)).toBeInTheDocument();
    expect(screen.getByText(/6\. Appearance Matching/i)).toBeInTheDocument();
  });
});
