import { expect, test } from '@playwright/test';

test.describe('Setup Wizard E2E Tests (Milestone A)', () => {
  test.beforeEach(async ({ page }) => {
    // 1. Mock Auth
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock_jwt_access_token_setup',
          token_type: 'bearer',
        }),
      });
    });

    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'usr_owner_01',
          username: 'admin',
          role: 'owner',
          active: true,
          created_at: 1793673891000,
          cameras: [],
        }),
      });
    });

    // 2. Mock Cameras
    await page.route('**/api/v1/cameras', async (route) => {
      if (route.request().method() === 'POST') {
        const body = JSON.parse(route.request().postData() || '{}');
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'cam_new_02',
            name: body.name,
            enabled: true,
            features: body.features || { vehicles: true, id_check: false },
            width: null,
            height: null,
            fps: null,
            status: 'unknown',
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'cam_01',
              name: 'Main Gate Entrance',
              enabled: true,
              features: { vehicles: true, id_check: false },
              width: 1920,
              height: 1080,
              fps: 30,
              status: 'online',
            },
          ]),
        });
      }
    });

    await page.route('**/api/v1/cameras/cam_01/test', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', width: 1920, height: 1080, fps: 30 }),
      });
    });

    await page.route('**/api/v1/cameras/cam_01', async (route) => {
      if (route.request().method() === 'PATCH') {
        const payload = JSON.parse(route.request().postData() || '{}');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'cam_01',
            name: payload.name || 'Main Gate Entrance',
            enabled: payload.enabled !== undefined ? payload.enabled : true,
            features: payload.features || { vehicles: true, id_check: false },
            width: 1920,
            height: 1080,
            fps: 30,
            status: 'online',
          }),
        });
      } else if (route.request().method() === 'DELETE') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'deleted', id: 'cam_01' }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'cam_01',
            name: 'Main Gate Entrance',
            enabled: true,
            features: { vehicles: true, id_check: false },
            width: 1920,
            height: 1080,
            fps: 30,
            status: 'online',
          }),
        });
      }
    });

    // 3. Mock Zones
    await page.route('**/api/v1/cameras/cam_01/zones', async (route) => {
      if (route.request().method() === 'POST') {
        const body = JSON.parse(route.request().postData() || '{}');
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: `zone_${Date.now()}`,
            camera_id: 'cam_01',
            name: body.name || 'Test Zone',
            kind: body.kind,
            shape: body.shape,
            points: body.points,
            direction: body.direction || null,
            is_read_area: body.is_read_area || false,
            enabled: true,
            created_at: 1793769000000,
            updated_at: 1793769000000,
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      }
    });

    // 4. Mock Templates & Presets
    await page.route('**/api/v1/rule-templates', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          templates: [],
          catalogue: {},
          operators: ['eq', 'neq'],
          severities: ['low', 'medium', 'critical'],
          presets: {},
        }),
      });
    });

    // 5. Mock Calendar Exemptions
    await page.route('**/api/v1/calendar', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    // 6. Mock Sample Clips
    await page.route('**/api/v1/actions/sample-clips', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'synth_heavy',
            name: 'Synthetic: Heavy Truck in Zone',
            path: 'backend/tests/synthetic/heavy_truck_in_zone.mp4',
            category: 'synthetic',
          },
        ]),
      });
    });

    // 7. Mock Dry-run draft & action
    await page.route('**/api/v1/actions/dry-run-draft', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          action_id: 'draft_action',
          rule_name: 'No heavy vehicles during restricted hours',
          total_frames_processed: 120,
          decisions_count: 3,
          decisions: [
            {
              kind: 'start',
              track_id: 1,
              ts_ms: 1793769000400,
              confidence: 0.88,
              evidence: { event_id: 'ev_01' },
              dry_run: true,
            },
            {
              kind: 'update',
              track_id: 1,
              ts_ms: 1793769001200,
              confidence: 0.92,
              evidence: {},
              dry_run: true,
            },
            {
              kind: 'end',
              track_id: 1,
              ts_ms: 1793769002800,
              confidence: 0.85,
              evidence: {},
              dry_run: true,
            },
          ],
        }),
      });
    });

    // 8. Mock Action Creation
    await page.route('**/api/v1/zones/*/actions', async (route) => {
      const body = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'action_01',
          zone_id: 'zone_spec_01',
          name: body.name || 'Heavy Vehicle Restriction',
          spec: body,
          severity: body.response?.severity || 'critical',
          enabled: true,
          created_at: 1793769000000,
          updated_at: 1793769000000,
        }),
      });
    });

    // 9. Mock Action Patch
    await page.route('**/api/v1/actions/action_*', async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'action_01',
            zone_id: 'zone_spec_01',
            name: 'Heavy Vehicle Restriction',
            spec: {},
            severity: 'critical',
            enabled: false,
            created_at: 1793769000000,
            updated_at: 1793769000000,
          }),
        });
      } else {
        await route.fallback();
      }
    });

    // Mock Alerts & Events list (used by AppShell)
    await page.route('**/api/v1/alerts*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    });
    await page.route('**/api/v1/events*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    });
  });

  test('normal zone gating: drawing a normal zone disables rule builder and finishes setup', async ({ page }) => {
    // 1. Login
    await page.goto('/');
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpass');
    await page.click('button[type="submit"]');

    // 2. Navigate to Setup & Rules
    await page.click('button:has-text("Setup & Rules")');
    await expect(page.getByTestId('setup-wizard')).toBeVisible();

    // 3. Step 1: Advance to Step 2
    await page.click('button[data-testid="btn-next-step-1"]');
    await expect(page.getByTestId('wizard-step-2')).toBeVisible();

    // 4. Select Normal zone
    await page.selectOption('select[data-testid="select-zone-kind"]', 'normal');
    await page.fill('input[data-testid="input-zone-name"]', 'Corridor Sighting Zone');

    // Verify explanation banner for normal zone
    await expect(page.getByText(/Normal Zone Rule Gating \(Enforced\)/i)).toBeVisible();

    // 5. Click Save Normal Zone & Finish
    const saveBtn = page.getByTestId('btn-save-zone');
    await expect(saveBtn).toHaveText(/Save Normal Zone & Finish/i);
    await saveBtn.click();

    // 6. Verify success status and that it does not proceed to rule builder
    await expect(page.getByTestId('status-message')).toBeVisible();
    await expect(page.getByText(/Normal zones only record sightings and cannot take rules/i)).toBeVisible();
    await expect(page.getByTestId('wizard-step-3')).not.toBeVisible();
  });

  test('special zone workflow: draw special zone, create heavy-vehicle rule, run dry run, arm rule', async ({ page }) => {
    // 1. Login
    await page.goto('/');
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpass');
    await page.click('button[type="submit"]');

    // 2. Navigate to Setup & Rules
    await page.click('button:has-text("Setup & Rules")');
    await expect(page.getByTestId('setup-wizard')).toBeVisible();

    // 3. Step 1: Camera Features
    await page.click('button[data-testid="btn-next-step-1"]');
    await expect(page.getByTestId('wizard-step-2')).toBeVisible();

    // 4. Step 2: Draw Special Zone
    await page.selectOption('select[data-testid="select-zone-kind"]', 'special');
    await page.fill('input[data-testid="input-zone-name"]', 'Loading Bay');
    await page.click('button[data-testid="btn-save-zone"]');

    // 5. Step 3: Rule Builder
    await expect(page.getByTestId('wizard-step-3')).toBeVisible();
    await expect(page.getByTestId('rule-builder')).toBeVisible();

    // Click Heavy Vehicle preset
    await page.click('button[data-testid="preset-heavy-vehicle"]');

    // Verify Live Sentence Summary
    const sentence = page.getByTestId('live-sentence-summary');
    await expect(sentence).toContainText('Raise a CRITICAL alert');
    await expect(sentence).toContainText("truck or bus stays in 'Loading Bay' for 2 s");
    await expect(sentence).toContainText('Mon-Sat 09:00-17:00');

    // Proceed to Step 4 (Dry Run & Arm)
    await page.click('button[data-testid="btn-next-step-3"]');
    await expect(page.getByTestId('wizard-step-4')).toBeVisible();

    // 6. Step 4: Run Dry Run Simulation
    await expect(page.getByTestId('dry-run-timeline-container')).toBeVisible();
    await page.click('button[data-testid="btn-run-dry-run"]');

    // Verify simulation results & timeline markers
    await expect(page.getByTestId('dry-run-results')).toBeVisible();
    await expect(page.getByText('Dry Run Simulation Report')).toBeVisible();
    await expect(page.getByTestId('timeline-marker-start')).toBeVisible();
    await expect(page.getByText(/0 alerts created, 0 database events recorded/i)).toBeVisible();

    // 7. Save and Arm Rule
    await page.click('button[data-testid="btn-save-and-arm"]');
    await expect(page.getByTestId('status-message')).toBeVisible();
    await expect(page.getByText(/successfully saved & armed \(Active\)/i)).toBeVisible();
  });

  test('camera management: view cameras tab, test stream, edit camera, add camera, and delete camera', async ({ page }) => {
    // 1. Login
    await page.goto('/');
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpass');
    await page.click('button[type="submit"]');

    // 2. Navigate to Setup & Rules -> Cameras Tab
    await page.click('button:has-text("Setup & Rules")');
    await page.click('button[data-testid="tab-cameras"]');
    await expect(page.getByTestId('cameras-manager')).toBeVisible();
    await expect(page.getByText('Camera Stream Management')).toBeVisible();
    await expect(page.getByText('Main Gate Entrance')).toBeVisible();

    // 3. Test Stream Connection
    await page.click('button[data-testid="test-camera-cam_01"]');
    await expect(page.getByText(/Live OK/i)).toBeVisible();

    // 4. Edit Camera
    await page.click('button[data-testid="edit-camera-cam_01"]');
    await expect(page.getByText('Edit Camera: Main Gate Entrance')).toBeVisible();
    await page.fill('input[data-testid="edit-camera-name"]', 'Main Gate Inbound');
    await page.click('button[data-testid="btn-save-edit-camera"]');
    await expect(page.getByTestId('cameras-message')).toBeVisible();

    // 5. Add Camera
    await page.click('button[data-testid="btn-add-camera"]');
    await expect(page.getByText('Register New Camera Stream')).toBeVisible();
    await page.fill('input[data-testid="input-camera-name"]', 'East Perimeter');
    await page.fill('input[data-testid="input-camera-rtsp"]', 'rtsp://admin:pass@192.168.1.120:554/live');
    await page.click('button[data-testid="btn-save-new-camera"]');
    await expect(page.getByTestId('cameras-message')).toBeVisible();

    // 6. Delete Camera
    await page.click('button[data-testid="delete-camera-cam_01"]');
    await expect(page.getByText(/Delete Camera 'Main Gate/i)).toBeVisible();
    await page.click('button[data-testid="confirm-delete-camera"]');
    await expect(page.getByTestId('cameras-message')).toBeVisible();
  });
});
