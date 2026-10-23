import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE_URL ?? '';
const FRONT_BASE = process.env.FRONT_BASE_URL ?? '';

const email = process.env.TEST_USER_EMAIL!;
const password = process.env.TEST_USER_PASSWORD!;
const firstName = process.env.TEST_USER_FIRST_NAME!;
const lastName = process.env.TEST_USER_LAST_NAME!;

test.describe('Settings: доступность информации о пользователе', () => {
  test('TC-SETTINGS-001: информация о пользователе доступна', async ({ page, request }) => {
    let accessToken: string;

    await test.step('Авторизоваться через API', async () => {
      const response = await request.post(`${API_BASE}/api/auth/login`, {
        data: { email, password },
      });

      expect(response.status()).toBe(200);

      const user = await response.json();
      accessToken = user.accessToken;

      expect(accessToken).toBeTruthy();

      await page.addInitScript((token) => {
        window.localStorage.setItem('accessToken', token);
      }, accessToken);
    });

    await test.step('Открыть страницу настроек', async () => {
      await page.goto(`${FRONT_BASE}/menu/settings`, {
        waitUntil: 'networkidle',
      });

      console.log('CURRENT URL:', page.url());

      await expect(page).toHaveURL(/\/menu\/settings$/);
      await expect(page.getByRole('heading', { name: 'Настройки' })).toBeVisible();
    });

    await test.step('Дождаться загрузки данных пользователя', async () => {
      await expect(page.getByPlaceholder(firstName)).toBeVisible({ timeout: 10_000 });
    });

    await test.step('Проверить значения в полях профиля', async () => {
      await expect(page.getByPlaceholder(firstName)).toHaveValue(firstName);
      await expect(page.getByPlaceholder(lastName)).toHaveValue(lastName);
      await expect(page.getByPlaceholder(email)).toHaveValue(email);
    });

    await test.step('Проверить данные после обновления страницы', async () => {
      await page.reload({ waitUntil: 'networkidle' });

      await expect(page).toHaveURL(/\/menu\/settings$/);

      await expect(page.getByPlaceholder(firstName)).toHaveValue(firstName);
      await expect(page.getByPlaceholder(lastName)).toHaveValue(lastName);
      await expect(page.getByPlaceholder(email)).toHaveValue(email);
    });

    await test.step('Проверить GET /api/user/me', async () => {
      const response = await request.get(`${API_BASE}/api/user/me`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      expect(response.status()).toBe(200);

      const user = await response.json();

      expect(user.userId).toBeTruthy();
      expect(user.email).toBe(email);
      expect(user.firstName).toBe(firstName);
      expect(user.lastName).toBe(lastName);

      expect(user).not.toHaveProperty('password');
      expect(user).not.toHaveProperty('passwordHash');
      expect(user).not.toHaveProperty('accessToken');
      expect(user).not.toHaveProperty('refreshToken');
    });
  });
});