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
});

