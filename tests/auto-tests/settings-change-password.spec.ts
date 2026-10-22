import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import * as path from 'node:path';
import { randomBytes } from 'node:crypto';

function requiredEnv(name: string): string {
  const value = process.env[name];

  if (!value) {
    throw new Error(`Не задана переменная окружения ${name}`);
  }

  return value;
}

test(
  'TC-PASSWORD-001: успешная смена пароля',
  async ({ page, request }, testInfo) => {
    const apiBase = requiredEnv('API_BASE_URL').replace(/\/$/, '');
    const frontBase = requiredEnv('FRONT_BASE_URL').replace(/\/$/, '');
    const email = requiredEnv('TEST_USER_EMAIL');
    const originalPassword = requiredEnv('TEST_USER_PASSWORD');

    // 18 символов: соответствует ограничению API 8–20.
    const newPassword = `Qa1!${randomBytes(7).toString('hex')}`;

    const screenshotsDir = path.resolve(process.cwd(), 'screenshots');

    await mkdir(screenshotsDir, { recursive: true });

    const runId = [
      new Date().toISOString().replace(/[:.]/g, '-'),
      'password-change',
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

    // В журнал не записываем пароли, токены и тело запроса.
    const login = (password: string) =>
      request.post(`${apiBase}/api/auth/login`, {
        data: { email, password },
      });

    const loginResponse = await login(originalPassword);

    expect(
      loginResponse.status(),
      'Не удалось войти с паролем из .env',
    ).toBe(200);

    const { accessToken } = await loginResponse.json();

    expect(accessToken).toBeTruthy();

    record('Вход с исходным паролем выполнен');

    await page.addInitScript(
      ({ token, origin }) => {
        if (
          window.location.origin === origin &&
          !window.sessionStorage.getItem('qa-auth-initialized')
        ) {
          window.localStorage.setItem('accessToken', token);
          window.sessionStorage.setItem(
            'qa-auth-initialized',
            'true',
          );
        }
      },
      {
        token: accessToken,
        origin: new URL(frontBase).origin,
      },
    );

    const dialogs: string[] = [];

    page.on('dialog', async (dialog) => {
      dialogs.push(dialog.message());

      // Сохраняем только факт получения уведомления.
      record('Получено браузерное уведомление', {
        type: dialog.type(),
      });

      await dialog.accept();
    });

    const panel = page.locator('.password-section');

    const oldPasswordInput =
      panel.getByPlaceholder('Ваш старый пароль', { exact: true });

    const newPasswordInput =
      panel.getByPlaceholder('Ваш новый пароль', { exact: true });

    const changeButton = panel.getByRole('button', {
      name: 'Изменить',
      exact: true,
    });

    const screenshot = async (name: string) => {
      const filename = `${runId}_${name}.png`;

      await panel.screenshot({
        path: path.join(screenshotsDir, filename),
        animations: 'disabled',
        mask: [oldPasswordInput, newPasswordInput],
      });

      record('Сохранён скриншот', { filename });
    };

    let saveAttempted = false;

    try {
      await test.step('Открыть панель смены пароля', async () => {
        await page.goto(`${frontBase}/menu/settings`);

        await expect(panel).toBeVisible();
        await expect(oldPasswordInput).toHaveValue('');
        await expect(newPasswordInput).toHaveValue('');

        await expect(oldPasswordInput).toHaveAttribute(
          'type',
          'password',
        );

        await expect(newPasswordInput).toHaveAttribute(
          'type',
          'password',
        );

        record('Панель открыта; поля пустые и скрывают символы');
        await screenshot('01-before');
      });

      await test.step('Ввести текущий и новый пароли', async () => {
        await oldPasswordInput.fill(originalPassword);
        await newPasswordInput.fill(newPassword);

        // Не сравниваем пароли через expect:
        // при падении проверки значения могли бы попасть в отчёт.
        const fieldsFilledCorrectly =
          (await oldPasswordInput.inputValue()) === originalPassword &&
          (await newPasswordInput.inputValue()) === newPassword;

        expect(
          fieldsFilledCorrectly,
          'Пароли должны быть введены в соответствующие поля',
        ).toBe(true);

        record('Текущий и новый пароли введены');
        await screenshot('02-filled');
      });

      await test.step('Сменить пароль через панель', async () => {
        saveAttempted = true;

        const responsePromise = page.waitForResponse(
          (response) =>
            new URL(response.url()).pathname ===
              '/api/user/change/password' &&
            ['PUT', 'POST', 'PATCH'].includes(
              response.request().method(),
            ),
        );

        record('Нажата кнопка «Изменить»');

        await changeButton.click();

        const response = await responsePromise;

        record('Получен ответ смены пароля', {
          method: response.request().method(),
          status: response.status(),
        });

        expect(response.request().method()).toBe('PUT');

        const body = response.request().postDataJSON();

        const bodyIsCorrect =
          body !== null &&
          typeof body === 'object' &&
          Object.keys(body).length === 2 &&
          body.lastPassword === originalPassword &&
          body.newPassword === newPassword;

        expect(
          bodyIsCorrect,
          'API должен получить lastPassword и newPassword',
        ).toBe(true);

        expect(response.status()).toBe(204);

        await expect
          .poll(() =>
            dialogs.includes('Пароль успешно изменён!'),
          )
          .toBe(true);

        record('Проверено сообщение «Пароль успешно изменён!»');

        await expect(oldPasswordInput).toHaveValue('');
        await expect(newPasswordInput).toHaveValue('');
        await expect(changeButton).toBeEnabled();

        record('Поля очищены после успешной смены');
        await screenshot('03-success');
      });

      await test.step('Проверить вход с новым паролем', async () => {
        const response = await login(newPassword);

        record('Проверен вход с новым паролем', {
          status: response.status(),
        });

        expect(response.status()).toBe(200);
      });

      await test.step('Проверить отказ во входе со старым паролем', async () => {
        const response = await login(originalPassword);

        record('Проверен вход со старым паролем', {
          status: response.status(),
        });

        expect(response.status()).toBe(401);
      });

      record('Основной сценарий успешно пройден');
    } catch (error) {
      // Не сохраняем полный текст ошибки:
      // он потенциально может содержать чувствительные данные.
      record('Основной сценарий завершился ошибкой');

      try {
        await screenshot('error');
      } catch {
        record('Скриншот ошибки недоступен');
      }

      throw error;
    } finally {
      try {
        if (saveAttempted) {
          await test.step('Восстановить исходный пароль', async () => {
            // Проверяем фактическое состояние даже если основной
            // сценарий упал после отправки запроса.
            const newLoginResponse = await login(newPassword);

            if (newLoginResponse.status() === 200) {
              const { accessToken: cleanupToken } =
                await newLoginResponse.json();

              const restoreResponse = await request.put(
                `${apiBase}/api/user/change/password`,
                {
                  headers: {
                    Authorization: `Bearer ${cleanupToken}`,
                  },
                  data: {
                    lastPassword: newPassword,
                    newPassword: originalPassword,
                  },
                },
              );

              record('Отправлен запрос восстановления пароля', {
                status: restoreResponse.status(),
              });

              expect(
                restoreResponse.status(),
                'Не удалось восстановить исходный пароль',
              ).toBe(204);
            } else {
              record(
                'Вход с новым паролем не выполнен; проверяем исходный',
                { status: newLoginResponse.status() },
              );
            }

            const verifyResponse = await login(originalPassword);

            expect(
              verifyResponse.status(),
              'Исходный пароль не подтверждён. Проверьте аккаунт вручную',
            ).toBe(200);

            record('Вход с исходным паролем подтверждён');
          });
        }
      } finally {
        await writeFile(
          path.join(screenshotsDir, `${runId}_actions.json`),
          JSON.stringify(
            {
              test: 'TC-PASSWORD-001',
              actions,
            },
            null,
            2,
          ),
          'utf8',
        );
      }
    }
  },
);