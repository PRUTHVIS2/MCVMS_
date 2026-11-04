import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as CamerasContext from '../../context/CamerasContext';
import * as apiModule from '../../services/api';
import { SetupPage } from './SetupPage';

vi.mock('../../services/api', () => ({
  api: {
    listCameras: vi.fn(),
    getCamera: vi.fn(),
    updateCamera: vi.fn(),
    getSnapshotUrl: vi.fn().mockReturnValue('/api/v1/cameras/cam_01/snapshot'),
    listZones: vi.fn(),
    createZone: vi.fn(),
    updateZone: vi.fn(),
    deleteZone: vi.fn(),
    listActions: vi.fn(),
    createAction: vi.fn(),
    updateAction: vi.fn(),
    deleteAction: vi.fn(),
    getRuleTemplates: vi.fn(),
    listSampleClips: vi.fn(),
    dryRunDraft: vi.fn(),
    dryRunAction: vi.fn(),
    listCalendarExemptions: vi.fn(),
    createCalendarExemption: vi.fn(),
    deleteCalendarExemption: vi.fn(),
  },
}));

describe('SetupPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.spyOn(CamerasContext, 'useCameras').mockReturnValue({
      cameras: [
        {
          id: 'cam_01',
          name: 'Main Gate Entrance',
          enabled: true,
          features: { vehicles: true, id_check: false },
          width: 1920,
          height: 1080,
          fps: 25,
          status: 'online',
        },
      ],
      activeCamera: null,
      setActiveCamera: vi.fn(),
      refreshCameras: vi.fn(),
      isLoading: false,
    });

    vi.spyOn(apiModule.api, 'listZones').mockResolvedValue([]);
    vi.spyOn(apiModule.api, 'getRuleTemplates').mockResolvedValue({
      templates: [],
      catalogue: {},
      operators: ['eq', 'neq'],
      severities: ['low', 'medium', 'critical'],
      presets: {},
    });
    vi.spyOn(apiModule.api, 'listCalendarExemptions').mockResolvedValue([]);
    vi.spyOn(apiModule.api, 'listSampleClips').mockResolvedValue([
      {
        id: 'synth_heavy',
        name: 'Synthetic: Heavy Truck in Zone',
        path: 'backend/tests/synthetic/heavy_truck_in_zone.mp4',
        category: 'synthetic',
      },
    ]);
  });

  it('renders top navigation tabs and switches between tabs', async () => {
    render(<SetupPage />);

    expect(screen.getByTestId('setup-wizard')).toBeInTheDocument();

    // Switch to Cameras tab
    const camerasTab = screen.getByTestId('tab-cameras');
    fireEvent.click(camerasTab);
    expect(screen.getByTestId('cameras-manager')).toBeInTheDocument();

    // Switch to Zones & Rules tab
    const managerTab = screen.getByTestId('tab-manager');
    fireEvent.click(managerTab);
    expect(screen.getByTestId('zones-rules-manager')).toBeInTheDocument();

    // Switch to Calendar Exemptions tab
    const calendarTab = screen.getByTestId('tab-calendar');
    fireEvent.click(calendarTab);
    expect(screen.getByTestId('calendar-exemptions-editor')).toBeInTheDocument();
  });

  it('allows moving from Step 1 (features) to Step 2 (draw zones)', async () => {
    vi.spyOn(apiModule.api, 'updateCamera').mockResolvedValue({
      id: 'cam_01',
      name: 'Main Gate Entrance',
      enabled: true,
      features: { vehicles: true, id_check: true },
      width: 1920,
      height: 1080,
      fps: 25,
      status: 'online',
    });

    render(<SetupPage />);

    expect(screen.getByTestId('wizard-step-1')).toBeInTheDocument();

    // Toggle ID check feature
    const idCheckSwitch = screen.getByTestId('switch-id-check');
    fireEvent.click(idCheckSwitch);

    // Click Continue
    const nextBtn = screen.getByTestId('btn-next-step-1');
    fireEvent.click(nextBtn);

    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-2')).toBeInTheDocument();
    });
  });

  it('enforces normal zone gating: saving a normal zone does not open rule builder', async () => {
    vi.spyOn(apiModule.api, 'updateCamera').mockResolvedValue({
      id: 'cam_01',
      name: 'Main Gate Entrance',
      enabled: true,
      features: { vehicles: true, id_check: false },
      width: 1920,
      height: 1080,
      fps: 25,
      status: 'online',
    });

    vi.spyOn(apiModule.api, 'createZone').mockResolvedValue({
      id: 'zone_norm_01',
      camera_id: 'cam_01',
      name: 'Corridor Traffic',
      kind: 'normal',
      shape: 'polygon',
      points: [
        [0.1, 0.1],
        [0.5, 0.1],
        [0.5, 0.5],
      ],
      is_read_area: false,
      enabled: true,
      created_at: 1793769000000,
      updated_at: 1793769000000,
    });

    render(<SetupPage />);

    // Move to Step 2
    fireEvent.click(screen.getByTestId('btn-next-step-1'));
    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-2')).toBeInTheDocument();
    });

    // Select Normal zone kind
    const kindSelect = screen.getByTestId('select-zone-kind');
    fireEvent.change(kindSelect, { target: { value: 'normal' } });

    // Verify explanation banner is visible
    expect(screen.getByText(/Normal Zone Rule Gating \(Enforced\)/i)).toBeInTheDocument();

    // Save Normal Zone
    const saveBtn = screen.getByTestId('btn-save-zone');
    expect(saveBtn.textContent).toContain('Save Normal Zone & Finish');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(apiModule.api.createZone).toHaveBeenCalledWith(
        'cam_01',
        expect.objectContaining({ kind: 'normal' })
      );
      expect(screen.getByTestId('status-message')).toBeInTheDocument();
    });
  });
});

