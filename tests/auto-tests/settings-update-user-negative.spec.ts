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

type Profile = {
  email: string;
  firstName: string;
  lastName: string;
};

const scenarios = [
  {
    id: 'invalid-email',
    title: 'Невалидный email',
    changes: { email: 'invalid-email' },
    clientValidation: false,
  },
  {
    id: 'empty-first-name',
    title: 'Пустое имя',
    changes: { firstName: '' },
    clientValidation: true,
  },
  {
    id: 'empty-last-name',
    title: 'Пустая фамилия',
    changes: { lastName: '' },
    clientValidation: true,
  },
  {
    id: 'empty-email',
    title: 'Пустой email',
    changes: { email: '' },
    clientValidation: true,
  },
  {
    id: 'all-empty',
    title: 'Все обязательные поля пустые',
    changes: {
      firstName: '',
      lastName: '',
      email: '',
    },
    clientValidation: true,
  },
] satisfies Array<{
  id: string;
  title: string;
  changes: Partial<Profile>;
  clientValidation: boolean;
}>;

test.describe('Профиль: проверка невалидных данных', () => {
  // Сценарии меняют один аккаунт — выполняем последовательно.
  test.describe.configure({ mode: 'default' });

  for (const scenario of scenarios) {
    test(scenario.title, async ({ page, request }, testInfo) => {
      const apiBase = requiredEnv('API_BASE_URL').replace(/\/$/, '');
      const frontBase = requiredEnv('FRONT_BASE_URL').replace(/\/$/, '');
      const email = requiredEnv('TEST_USER_EMAIL');
      const password = requiredEnv('TEST_USER_PASSWORD');

      const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
      await mkdir(screenshotsDir, { recursive: true });

      const prefix = [
        new Date().toISOString().replace(/[:.]/g, '-'),
        scenario.id,
        `worker-${testInfo.workerIndex}`,
        `retry-${testInfo.retry}`,
      ].join('_');

      const log: Array<{
        time: string;
        action: string;
        details?: unknown;
      }> = [];

      const record = (action: string, details?: unknown) => {
        log.push({
          time: new Date().toISOString(),
          action,
          details,
        });
      };

      const loginResponse = await request.post(
        `${apiBase}/api/auth/login`,
        { data: { email, password } },
      );

      expect(loginResponse.status(), 'Ошибка авторизации').toBe(200);

      const { accessToken } = await loginResponse.json();

      expect(accessToken).toBeTruthy();

      const headers = {
        Authorization: `Bearer ${accessToken}`,
      };

      const getProfile = async (): Promise<Profile> => {
        const response = await request.get(
          `${apiBase}/api/user/me`,
          { headers },
        );

        expect(response.status()).toBe(200);

        const body = await response.json();

        return {
          email: body.email,
          firstName: body.firstName,
          lastName: body.lastName,
        };
      };

      const originalProfile = await getProfile();
      const submittedProfile = {
        ...originalProfile,
        ...scenario.changes,
      };

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

        record('Получено браузерное уведомление', {
          type: dialog.type(),
          message: dialog.message(),
        });

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

      const checkFields = async (expected: Profile) => {
        await expect(firstNameInput).toHaveValue(expected.firstName);
        await expect(lastNameInput).toHaveValue(expected.lastName);
        await expect(emailInput).toHaveValue(expected.email);
      };

      const screenshot = async (name: string) => {
        const filename = `${prefix}_${name}.png`;

        await profile.screenshot({
          path: path.join(screenshotsDir, filename),
          animations: 'disabled',
        });

        record('Сохранён скриншот', { filename });
      };

      // Фиксируем запросы именно на изменение профиля.
      const updates: Array<{
        method: string;
        body: unknown;
        status?: number;
      }> = [];

      const trackedRequests = new Map<object, number>();

      page.on('request', (req) => {
        if (
          new URL(req.url()).pathname === '/api/user/change/personal' &&
          ['PUT', 'POST', 'PATCH'].includes(req.method())
        ) {
          const entry = {
            method: req.method(),
            body: req.postData(),
          };

          trackedRequests.set(req, updates.length);
          updates.push(entry);

          record('Отправлен запрос изменения профиля', entry);
        }
      });

      page.on('response', (response) => {
        const index = trackedRequests.get(response.request());

        if (index !== undefined) {
          updates[index].status = response.status();

          record('Получен ответ изменения профиля', {
            status: response.status(),
          });
        }
      });

      let saveAttempted = false;

      try {
        await test.step('Открыть профиль и зафиксировать исходные данные', async () => {
          await page.goto(`${frontBase}/menu/settings`);

          await expect(profile).toBeVisible();
          await checkFields(originalProfile);

          record('Профиль открыт', originalProfile);
          await screenshot('01-before');
        });

        await test.step('Ввести невалидные данные', async () => {
          await firstNameInput.fill(submittedProfile.firstName);
          await lastNameInput.fill(submittedProfile.lastName);
          await emailInput.fill(submittedProfile.email);

          await checkFields(submittedProfile);

          record('Введены тестовые данные', submittedProfile);
          await screenshot('02-invalid-input');
        });

        await test.step('Нажать «Применить» и проверить отказ', async () => {
          saveAttempted = true;
          record('Нажатие кнопки «Применить»');

          await profile
            .getByRole('button', {
              name: 'Применить',
              exact: true,
            })
            .click();

          // В присланном SettingsPage все результаты выводятся через alert.
          // Ждём уведомление, а не используем фиксированную задержку.
          await expect
            .poll(() => dialogs.length, {
              message: 'Ожидалось уведомление о результате сохранения',
              timeout: 10_000,
            })
            .toBeGreaterThan(0);

          await expect(
            profile.getByRole('button', {
              name: 'Применить',
              exact: true,
            }),
          ).toBeEnabled();

          await screenshot('03-after-submit');

          expect(
            dialogs,
            'Не должно быть сообщения об успешном обновлении',
          ).not.toContain('Профиль успешно обновлён!');

          if (scenario.clientValidation) {
            expect(dialogs).toContain(
              'Все поля профиля должны быть заполнены!',
            );

            expect(
              updates,
              'При пустых полях frontend не должен отправлять запрос',
            ).toHaveLength(0);
          } else {
            // Невалидный email может отклонить frontend или backend.
            // Если запрос ушёл — ожидаем отказ валидации 400.
            await expect
              .poll(() =>
                updates.every((update) => update.status !== undefined),
              )
              .toBe(true);

            for (const update of updates) {
              expect(update.method).toBe('PUT');
              expect(
                update.status,
                'Невалидный email должен отклоняться с 400',
              ).toBe(400);
            }
          }
        });

        await test.step('Проверить, что данные аккаунта не изменились', async () => {
          const currentProfile = await getProfile();

          record('Профиль после попытки сохранения', currentProfile);

          expect(currentProfile).toEqual(originalProfile);

          await page.reload();
          await checkFields(originalProfile);

          await screenshot('04-unchanged-after-reload');
        });

        record('Результат', 'Негативный сценарий успешно пройден');
      } catch (error) {
        record(
          'Тест завершился ошибкой',
          error instanceof Error ? error.message : String(error),
        );

        // Скриншот ошибки не должен мешать восстановлению аккаунта.
        try {
          await screenshot('error');
        } catch {
          record('Скриншот ошибки недоступен');
        }

        throw error;
      } finally {
        try {
          if (saveAttempted) {
            // Если из-за дефекта данные всё-таки изменились,
            // пытаемся восстановить профиль.
            let cleanupToken = accessToken;

            for (const loginEmail of [
              originalProfile.email,
              submittedProfile.email,
            ]) {
              const response = await request.post(
                `${apiBase}/api/auth/login`,
                {
                  data: { email: loginEmail, password },
                },
              );

              if (response.status() === 200) {
                cleanupToken = (await response.json()).accessToken;
                break;
              }
            }

            const cleanupHeaders = {
              Authorization: `Bearer ${cleanupToken}`,
            };

            const currentResponse = await request.get(
              `${apiBase}/api/user/me`,
              { headers: cleanupHeaders },
            );

            expect(
              currentResponse.status(),
              'Не удалось проверить профиль после теста',
            ).toBe(200);

            const current = await currentResponse.json();

            const changed =
              current.email !== originalProfile.email ||
              current.firstName !== originalProfile.firstName ||
              current.lastName !== originalProfile.lastName;

            if (changed) {
              record('Обнаружены изменения — восстановление профиля');

              const restoreResponse = await request.put(
                `${apiBase}/api/user/change/personal`,
                {
                  headers: cleanupHeaders,
                  data: originalProfile,
                },
              );

              expect(
                restoreResponse.status(),
                'Восстановите данные аккаунта вручную',
              ).toBe(204);

              record('Исходный профиль отправлен на восстановление');
            } else {
              record('Восстановление не требуется: профиль не изменён');
            }
          }
        } finally {
          // Записываем журнал даже при падении теста или очистки.
          await writeFile(
            path.join(screenshotsDir, `${prefix}_actions.json`),
            JSON.stringify(
              {
                scenario: scenario.title,
                actions: log,
                updateRequests: updates,
              },
              null,
              2,
            ),
            'utf8',
          );
        }
      }
    });
  }
});