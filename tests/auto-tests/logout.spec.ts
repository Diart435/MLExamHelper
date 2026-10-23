import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import * as path from 'node:path';

function requiredEnv(name: string): string {
  const value = process.env[name];

  if (!value) {
    throw new Error(`Не задана переменная окружения ${name}`);
  }

  return value;
}

// Уточните по маршрутам и разметке вашего приложения.
const LOGIN_PATH = '/login';
const PROTECTED_PATH = '/menu/settings';
const LOGOUT_BUTTON_NAME = 'Выйти';

test('TC-LOGOUT-001: выход из аккаунта', async (
  { browser, request },
  testInfo,
) => {
  const apiBase = requiredEnv('API_BASE_URL').replace(/\/$/, '');
  const frontBase = requiredEnv('FRONT_BASE_URL').replace(/\/$/, '');

  const email = requiredEnv('TEST_USER_EMAIL');
  const password = requiredEnv('TEST_USER_PASSWORD');

  const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
  await mkdir(screenshotsDir, { recursive: true });

  const prefix = [
    new Date().toISOString().replace(/[:.]/g, '-'),
    'logout',
    `worker-${testInfo.workerIndex}`,
    `retry-${testInfo.retry}`,
  ].join('_');

  const actions: Array<{
    time: string;
    action: string;
    details?: unknown;
  }> = [];

  const record = (action: string, details?: unknown) => {
    actions.push({
      time: new Date().toISOString(),
      action,
      details,
    });
  };

  // Авторизация выполняется до создания браузерного контекста.
  const loginResponse = await request.post(
    `${apiBase}/api/auth/login`,
    {
      data: { email, password },
    },
  );

  expect(
    loginResponse.status(),
    'Не удалось авторизоваться с данными из .env',
  ).toBe(200);

  const { accessToken } = await loginResponse.json();

  expect(
    typeof accessToken === 'string' && accessToken.length > 0,
    'Login API должен вернуть accessToken',
  ).toBe(true);

  record('Авторизация через API выполнена');

  // Токен задаётся только при создании контекста.
  // После logout тест больше нигде его не устанавливает.
  const context = await browser.newContext({
    baseURL: frontBase,
    storageState: {
      cookies: [],
      origins: [
        {
          origin: new URL(frontBase).origin,
          localStorage: [
            {
              name: 'accessToken',
              value: accessToken,
            },
          ],
        },
      ],
    },
  });

  const page = await context.newPage();

  const profile = page.locator('.profile-section');

  const logoutButton = page.getByRole('button', {
    name: LOGOUT_BUTTON_NAME,
    exact: true,
  });

  // Подходит для обычного маршрута, например /login.
  const isLoginPage = (url: URL) =>
    url.origin === new URL(frontBase).origin &&
    url.pathname.replace(/\/+$/, '') ===
      LOGIN_PATH.replace(/\/+$/, '');

  const screenshot = async (name: string) => {
    const filename = `${prefix}_${name}.png`;

    await page.screenshot({
      path: path.join(screenshotsDir, filename),
      fullPage: true,
      animations: 'disabled',
      mask: [page.locator('input')],
    });

    record('Сохранён скриншот', { filename });
  };

  const expectTokenRemoved = async () => {
    await expect
      .poll(
        () =>
          page.evaluate(() =>
            window.localStorage.getItem('accessToken'),
          ),
        {
          message: 'После выхода accessToken должен быть удалён',
        },
      )
      .toBeNull();
  };

  const expectLoggedOut = async () => {
    await expect(
      page,
      'Ожидалось перенаправление на страницу входа',
    ).toHaveURL(isLoginPage);

    await expect(profile).not.toBeVisible();
    await expect(logoutButton).not.toBeVisible();

    await expectTokenRemoved();
  };

  try {
    await test.step('Открыть настройки авторизованного пользователя', async () => {
      await page.goto(PROTECTED_PATH);

      await expect(profile).toBeVisible();
      await expect(logoutButton).toBeVisible();
      await expect(logoutButton).toBeEnabled();

      const tokenPresent = await page.evaluate(
        () => Boolean(window.localStorage.getItem('accessToken')),
      );

      expect(tokenPresent).toBe(true);

      record('Открыт защищённый раздел, пользователь авторизован');
      await screenshot('01-authorized');
    });

    await test.step('Выйти через интерфейс', async () => {
      record('Нажата кнопка выхода');

      await logoutButton.click();

      await expectLoggedOut();

      record(
        'Выход выполнен: токен удалён, открыта страница входа',
      );

      await screenshot('02-after-logout');
    });

    await test.step('Проверить состояние после обновления страницы', async () => {
      await page.reload();

      await expectLoggedOut();

      record('После обновления пользователь остаётся неавторизованным');
      await screenshot('03-after-reload');
    });

    await test.step('Проверить прямой переход в защищённый раздел', async () => {
      await page.goto(PROTECTED_PATH);

      await expectLoggedOut();

      record(
        'Прямой переход в настройки перенаправляет на страницу входа',
      );

      await screenshot('04-protected-route-blocked');
    });

    record('Тест успешно пройден');
  } catch (error) {
    record('Тест завершился ошибкой');

    try {
      await screenshot('error');
    } catch {
      record('Не удалось сохранить скриншот ошибки');
    }

    throw error;
  } finally {
    try {
      await writeFile(
        path.join(screenshotsDir, `${prefix}_actions.json`),
        JSON.stringify(
          {
            test: 'TC-LOGOUT-001',
            actions,
          },
          null,
          2,
        ),
        'utf8',
      );
    } finally {
      await context.close();
    }
  }
});