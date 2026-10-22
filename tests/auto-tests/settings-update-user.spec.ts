import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import * as path from 'node:path';

function requiredEnv(name: string): string {
  const value = process.env[name];

  if (!value) {
    throw new Error(`Не задана переменная окружения ${name}`);
  }

  return value;
}

test(
  'TC-PROFILE-002: изменение информации о пользователе',
  async ({ page, request }, testInfo) => {
    const apiBase = requiredEnv('API_BASE_URL').replace(/\/$/, '');
    const frontBase = requiredEnv('FRONT_BASE_URL').replace(/\/$/, '');
    const email = requiredEnv('TEST_USER_EMAIL');
    const password = requiredEnv('TEST_USER_PASSWORD');

    const screenshotsDir = path.resolve(process.cwd(), 'screenshots');

    await mkdir(screenshotsDir, { recursive: true });

    // Уникальный префикс: предыдущие скриншоты не перезаписываются.
    const runId = [
      new Date().toISOString().replace(/[:.]/g, '-'),
      `worker-${testInfo.workerIndex}`,
      `retry-${testInfo.retry}`,
    ].join('_');

    // Авторизация.
    const loginResponse = await request.post(
      `${apiBase}/api/auth/login`,
      {
        data: { email, password },
      },
    );

    expect(loginResponse.status(), 'Ошибка авторизации').toBe(200);

    const { accessToken } = await loginResponse.json();

    expect(accessToken).toBeTruthy();

    const headers = {
      Authorization: `Bearer ${accessToken}`,
    };

    // Сохраняем исходные данные пользователя.
    const meResponse = await request.get(`${apiBase}/api/user/me`, {
      headers,
    });

    expect(meResponse.status()).toBe(200);

    const original = await meResponse.json();

    const originalProfile = {
      email: original.email,
      firstName: original.firstName,
      lastName: original.lastName,
    };

    const updatedProfile = {
      email: `qaprofile.${Date.now()}@example.com`,
      firstName: 'ТестовоеИмя',
      lastName: 'ТестоваяФамилия',
    };

    const frontOrigin = new URL(frontBase).origin;

    // Записываем токен только при первом открытии frontend.
    // При перезагрузках не перезаписываем токен приложения.
    await page.addInitScript(
      ({ token, origin }) => {
        if (
          window.location.origin === origin &&
          !window.sessionStorage.getItem('qa-auth-initialized')
        ) {
          window.localStorage.setItem('accessToken', token);
          window.sessionStorage.setItem('qa-auth-initialized', 'true');
        }
      },
      {
        token: accessToken,
        origin: frontOrigin,
      },
    );

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    const profile = page.locator('.profile-section');

    const field = (label: string) =>
      profile
        .locator('.input-group')
        .filter({
          has: page.locator('label', {
            hasText: new RegExp(`^${label}$`),
          }),
        })
        .locator('input');

    const firstNameInput = field('Изменить имя');
    const lastNameInput = field('Изменить фамилию');
    const emailInput = field('Изменить почту');

    const checkProfile = async (expected: typeof originalProfile) => {
      await expect(firstNameInput).toHaveValue(expected.firstName);
      await expect(lastNameInput).toHaveValue(expected.lastName);
      await expect(emailInput).toHaveValue(expected.email);
    };

    const saveScreenshot = async (name: string) => {
      await profile.screenshot({
        path: path.join(screenshotsDir, `${runId}_${name}.png`),
        animations: 'disabled',
      });
    };

    let saveAttempted = false;

    try {
      await test.step(
        'Открыть профиль и сделать скриншот исходных данных',
        async () => {
          await page.goto(`${frontBase}/menu/settings`);

          await expect(
            page.getByRole('heading', {
              name: 'Настройки',
              exact: true,
            }),
          ).toBeVisible();

          await checkProfile(originalProfile);

          await saveScreenshot('01-before');
        },
      );

      await test.step('Изменить имя, фамилию и email', async () => {
        await firstNameInput.fill(updatedProfile.firstName);
        await lastNameInput.fill(updatedProfile.lastName);
        await emailInput.fill(updatedProfile.email);

        saveAttempted = true;

        const responsePromise = page.waitForResponse(
          (response) =>
            new URL(response.url()).pathname ===
              '/api/user/change/personal' &&
            ['PUT', 'POST', 'PATCH'].includes(
              response.request().method(),
            ),
        );

        await profile
          .getByRole('button', {
            name: 'Применить',
            exact: true,
          })
          .click();

        const response = await responsePromise;

        expect(response.request().method()).toBe('PUT');
        expect(response.request().postDataJSON()).toEqual(
          updatedProfile,
        );
        expect(response.status()).toBe(204);
      });

      await test.step('Проверить изменения через API', async () => {
        const response = await request.get(
          `${apiBase}/api/user/me`,
          { headers },
        );

        expect(response.status()).toBe(200);

        expect(await response.json()).toMatchObject({
          userId: original.userId,
          ...updatedProfile,
        });
      });

      await test.step(
        'Проверить изменения после перезагрузки и сделать скриншот',
        async () => {
          await page.reload();

          await expect(page).toHaveURL(/\/menu\/settings\/?$/);
          await checkProfile(updatedProfile);

          await saveScreenshot('02-after-reload');
        },
      );
    } finally {
      if (saveAttempted) {
        await test.step('Восстановить исходные данные', async () => {
          let cleanupToken = accessToken;

          // После изменения email получаем свежий токен.
          // Если сохранение не произошло, пробуем исходный email.
          for (const loginEmail of [
            updatedProfile.email,
            originalProfile.email,
          ]) {
            const response = await request.post(
              `${apiBase}/api/auth/login`,
              {
                data: {
                  email: loginEmail,
                  password,
                },
              },
            );

            if (response.status() === 200) {
              cleanupToken = (await response.json()).accessToken;
              break;
            }
          }

          const restoreResponse = await request.put(
            `${apiBase}/api/user/change/personal`,
            {
              headers: {
                Authorization: `Bearer ${cleanupToken}`,
              },
              data: originalProfile,
            },
          );

          expect(
            restoreResponse.status(),
            'Не удалось восстановить исходный профиль',
          ).toBe(204);

          // Входим с исходным email после восстановления.
          const restoredLoginResponse = await request.post(
            `${apiBase}/api/auth/login`,
            {
              data: {
                email: originalProfile.email,
                password,
              },
            },
          );

          expect(restoredLoginResponse.status()).toBe(200);

          const restoredToken =
            (await restoredLoginResponse.json()).accessToken;

          const verifyResponse = await request.get(
            `${apiBase}/api/user/me`,
            {
              headers: {
                Authorization: `Bearer ${restoredToken}`,
              },
            },
          );

          expect(verifyResponse.status()).toBe(200);
          expect(await verifyResponse.json()).toMatchObject(
            originalProfile,
          );

          // Обновляем токен браузера для проверки восстановленного UI.
          await page.goto(`${frontBase}/menu/settings`);

          await page.evaluate((token) => {
            window.localStorage.setItem('accessToken', token);
          }, restoredToken);

          await page.reload();

          await expect(page).toHaveURL(/\/menu\/settings\/?$/);
          await checkProfile(originalProfile);

          await saveScreenshot('03-restored');
        });
      }
    }
  },
);