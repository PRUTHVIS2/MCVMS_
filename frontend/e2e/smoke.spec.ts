import { test, expect } from '@playwright/test';

test.describe('MCVMS Frontend Smoke Tests (Mocked Backend)', () => {
  test.beforeEach(async ({ page }) => {
    // 1. Mock Auth endpoints
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock_jwt_access_token_123',
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

    // 2. Mock Cameras endpoints
    await page.route('**/api/v1/cameras', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'cam_01',
            name: 'North Gate Cam',
            enabled: true,
            features: { vehicles: true, id_check: false },
            width: 1920,
            height: 1080,
            fps: 30,
            status: 'online',
          },
          {
            id: 'cam_02',
            name: 'South Exit Cam',
            enabled: true,
            features: { vehicles: true, id_check: true },
            width: 1920,
            height: 1080,
            fps: 25,
            status: 'offline',
          },
        ]),
      });
    });

    // 3. Mock Zones endpoints
    await page.route('**/api/v1/cameras/*/zones', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'zone_spec_01',
            camera_id: 'cam_01',
            name: 'Loading Bay Zone',
            kind: 'special',
            shape: 'polygon',
            points: [
              [0.1, 0.1],
              [0.5, 0.1],
              [0.5, 0.5],
              [0.1, 0.5],
            ],
            direction: null,
            is_read_area: false,
            enabled: true,
            created_at: 1793673891000,
            updated_at: 1793673891000,
          },
        ]),
      });
    });

    // 4. Mock Stream info
    await page.route('**/api/v1/cameras/*/stream-info', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          camera_id: 'cam_01',
          name: 'North Gate Cam',
          status: 'online',
          webrtc_url: 'http://localhost:8889/cam_01/whep',
          hls_url: 'http://localhost:8888/cam_01/index.m3u8',
          width: 1920,
          height: 1080,
          fps: 30,
        }),
      });
    });

    // 5. Mock Alerts endpoints
    await page.route('**/api/v1/alerts*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'alt_01',
            camera_id: 'cam_01',
            camera_name: 'North Gate Cam',
            zone_name: 'Loading Bay Zone',
            level: 'critical',
            message: 'Heavy vehicle in Loading Bay Zone',
            status: 'open',
            opened_at: 1793673891000,
          },
        ]),
      });
    });

    // 6. Mock Events endpoints
    await page.route('**/api/v1/events*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'evt_01',
            camera_id: 'cam_01',
            camera_name: 'North Gate Cam',
            zone_id: 'zone_spec_01',
            zone_name: 'Loading Bay Zone',
            severity: 'critical',
            kind: 'heavy_vehicle',
            status: 'open',
            started_at: 1793673891000,
            ended_at: 1793673926000,
            subject: { category: 'truck', colour: 'white', plate: 'KA05AB1234' },
            confidence: 0.94,
            clip_id: 'clip_01',
          },
        ]),
      });
    });

    // 7. Mock System endpoints
    await page.route('**/api/v1/system/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          timestamp: 1793673891000,
          cameras: [
            {
              id: 'cam_01',
              name: 'North Gate Cam',
              enabled: true,
              fps: 30,
              width: 1920,
              height: 1080,
              status: 'online',
              features: { vehicles: true, id_check: false },
            },
          ],
          disk: {
            total_gb: 500.0,
            free_gb: 380.0,
            used_gb: 120.0,
            percent_used: 24.0,
            status: 'ok',
          },
          gpu: {
            available: true,
            device: 'cuda',
            name: 'NVIDIA GeForce RTX 3080',
            memory_used_mb: 2150,
            memory_total_mb: 10240,
          },
          decode_errors: { cam_01: 0 },
        }),
      });
    });

    await page.route('**/api/v1/system/config-summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          app: { timezone: 'Asia/Kolkata', mode: 'live', device: 'cuda' },
          model: { weights: 'yolo11n.pt', tracker: 'bytetrack.yaml' },
          heavy_categories: ['truck', 'bus'],
          clips: { retry_limit: 5, retry_interval_s: 5.0, segment_gap_tolerance_ms: 2500 },
          retention: { video_days: 7 },
        }),
      });
    });

    // 8. Mock Users and Audit endpoints
    await page.route('**/api/v1/users*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'u1', username: 'admin', role: 'owner', active: true, cameras: [], created_at: 1793673891000 },
          { id: 'u2', username: 'guard1', role: 'guard', active: true, cameras: ['cam_01'], created_at: 1793673891000 },
        ]),
      });
    });

    await page.route('**/api/v1/audit*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 1,
            ts: 1793673891000,
            user_id: 'u1',
            username: 'admin',
            action: 'user.login',
            target: 'auth',
            detail: { ip: '127.0.0.1' },
          },
        ]),
      });
    });
  });

  test('login and render live wall with camera status and overlay', async ({ page }) => {
    // 1. Visit App
    await page.goto('/');

    // 2. Verify Login Page & Styling
    await expect(page.getByRole('heading', { name: /MCVMS/i })).toBeVisible();
    await expect(page.getByText('Multi-Camera Video Management System')).toBeVisible();

    const submitBtn = page.locator('button[type="submit"]');
    const btnBg = await submitBtn.evaluate((el) => window.getComputedStyle(el).backgroundColor);
    // Ensure button is styled with amber background (not default transparent/browser default)
    expect(btnBg).not.toBe('rgba(0, 0, 0, 0)');
    expect(btnBg).not.toBe('transparent');

    // 3. Perform Login
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpass');
    await page.click('button[type="submit"]');

    // 4. Verify Shell & Navigation
    await expect(page.getByText('Live Wall')).toBeVisible();
    await expect(page.getByText('admin')).toBeVisible();
    await expect(page.getByText('owner')).toBeVisible();

    // 5. Verify Live Wall Content
    await expect(page.getByText('2 Cameras')).toBeVisible();
    await expect(page.getByText('1 Online')).toBeVisible();
    await expect(page.getByText('1 Offline')).toBeVisible();
    await expect(page.getByText('North Gate Cam')).toBeVisible();
    await expect(page.getByText('South Exit Cam')).toBeVisible();

    // 6. Verify Overlay Canvas is present
    const canvases = page.locator('canvas[data-testid="camera-overlay-canvas"]');
    await expect(canvases).toHaveCount(2);

    // 7. Verify Alert Bell shows count badge
    const alertBadge = page.locator('[data-testid="alert-bell-badge"]');
    await expect(alertBadge).toBeVisible();
    await expect(alertBadge).toHaveText('1');

    // 8. Open Alert Popover
    await page.click('button[aria-label="Alerts"]');
    await expect(page.getByText('System Alerts')).toBeVisible();
    await expect(page.getByText('Heavy vehicle in Loading Bay Zone')).toBeVisible();
  });

  test('events review, clip player with 15s pre-roll trigger marker, and drawer interaction', async ({ page }) => {
    await page.goto('/');
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpass');
    await page.click('button[type="submit"]');

    // Navigate to Events Page
    await page.click('button:has-text("Events")');
    await expect(page.getByText('Timestamp (IST)')).toBeVisible();

    // Verify Event Row
    const eventRow = page.getByTestId('event-row-evt_01');
    await expect(eventRow).toBeVisible();
    await expect(eventRow.getByText('North Gate Cam')).toBeVisible();
    await expect(eventRow.getByText('heavy vehicle')).toBeVisible();
    await expect(eventRow.getByText(/KA05AB1234/)).toBeVisible();

    // Open Event Detail Drawer
    await eventRow.click();
    await expect(page.getByTestId('event-detail-drawer')).toBeVisible();
    await expect(page.getByTestId('event-clip-player')).toBeVisible();
    await expect(page.getByText(/Trigger Point: 15s/i)).toBeVisible();

    // Verify Subject Attributes card
    const drawer = page.getByTestId('event-detail-drawer');
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText('KA05AB1234')).toBeVisible();
    await expect(drawer.getByRole('button', { name: 'Acknowledge' })).toBeVisible();
    await expect(drawer.getByRole('button', { name: 'Mark False Alarm' })).toBeVisible();
  });

  test('system health diagnostics, active model and accuracy constraints', async ({ page }) => {
    await page.goto('/');
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpass');
    await page.click('button[type="submit"]');

    // Navigate to System Page
    await page.click('button:has-text("System")');
    await expect(page.getByRole('heading', { name: 'System Health & Metrics' })).toBeVisible();

    // Verify Top Stat Cards
    await expect(page.getByText('Storage & Data Disk')).toBeVisible();
    await expect(page.getByText('380 GB')).toBeVisible();
    await expect(page.getByText('NVIDIA GeForce RTX 3080')).toBeVisible();

    // Verify Configuration Summary
    await expect(page.getByText('Configuration Summary')).toBeVisible();
    await expect(page.getByText('yolo11n.pt')).toBeVisible();

    // Verify "About accuracy" section is not displayed
    await expect(page.getByTestId('about-accuracy-section')).not.toBeVisible();
  });

  test('user management and audit log feed for owner', async ({ page }) => {
    await page.goto('/');
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpass');
    await page.click('button[type="submit"]');

    // Navigate to Users & Audit Page
    await page.click('button:has-text("Users & Audit")');
    await expect(page.getByText('User Management')).toBeVisible();
    await expect(page.getByText('Add New User')).toBeVisible();

    // Check user table
    await expect(page.getByText('guard1')).toBeVisible();

    // Switch to Audit Log tab
    await page.click('button:has-text("Audit Log Feed")');
    await expect(page.getByText('user.login')).toBeVisible();
    await expect(page.getByText(/127\.0\.0\.1/)).toBeVisible();
  });
});

