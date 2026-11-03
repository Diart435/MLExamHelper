import { test, expect, type APIRequestContext } from '@playwright/test';
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

test.use({
  trace: 'off',
  video: 'off',
  screenshot: 'off',
});

test(
  'TC-COURSES-CREATE-001: успешное создание курса',
  async ({ page, playwright }, testInfo) => {
    const apiBase = requiredEnv('API_BASE_URL').replace(/\/$/, '');

    const courseName = `QA Автотест ${randomBytes(4).toString('hex')}`;
    const courseDescription =
      'Курс создан автоматическим тестом и должен быть удалён после проверки.';

    const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
    await mkdir(screenshotsDir, { recursive: true });

    const prefix = [
      new Date().toISOString().replace(/[:.]/g, '-'),
      'course-create',
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

    // Отдельный API-контекст для очистки:
    // он остаётся доступен, даже если браузер закрылся по таймауту.
    const apiContext: APIRequestContext =
      await playwright.request.newContext({
        baseURL: apiBase,
      });

    let createdCourseId: string | null = null;

    const emailInput = page.locator(
      'input[type="email"], input[name="email"], input[placeholder*="mail" i]',
    );

    const passwordInput = page.locator('input[type="password"]');

    const loginButton = page.getByRole('button', {
      name: /войти|авторизоваться|log in|sign in/i,
    });

    const pageRoot = page.locator('.courses-page');
    const grid = page.locator('.courses-grid');
    const cards = grid.locator('.course-card');

    const searchInput = page.getByPlaceholder(
      'Поиск по курсам...',
      { exact: true },
    );

    const modal = page.getByRole('dialog');
    const nameInput = modal.locator('#cc-name');
    const descriptionInput = modal.locator('#cc-desc');

    const createButton = modal.getByRole('button', {
      name: 'Создать курс',
      exact: true,
    });

    const findCreatedCourse = () =>
      cards.filter({
        has: page.locator('.card-title', {
          hasText: courseName,
        }),
      });

    const screenshot = async (name: string) => {
      const filename = `${prefix}_${name}.png`;

      await pageRoot
        .isVisible()
        .then(async (visible) => {
          const target = visible ? pageRoot : page;

          await target.screenshot({
            path: path.join(screenshotsDir, filename),
            fullPage: true,
            animations: 'disabled',
          });
        })
        .catch(() => {
          record('Скриншот недоступен', { filename });
        });

      record('Сохранён скриншот', { filename });
    };

    const authorize = async () => {
      await page.goto('/');

      const alreadyAuthorized = await pageRoot
        .isVisible()
        .catch(() => false);

      if (alreadyAuthorized) {
        record('Пользователь уже авторизован');
        return;
      }

      await expect(emailInput.first()).toBeVisible({
        timeout: 20_000,
      });

      await emailInput
        .first()
        .fill(requiredEnv('TEST_USER_EMAIL'));

      await passwordInput
        .first()
        .fill(requiredEnv('TEST_USER_PASSWORD'));

      record('Введены данные для входа');
      await screenshot('01-login-filled');

      await loginButton.first().click();

      await expect
        .poll(
          async () =>
            (await pageRoot.isVisible().catch(() => false)) ||
            !(await passwordInput
              .first()
              .isVisible()
              .catch(() => true)),
          {
            timeout: 30_000,
            message: 'Ожидалась авторизация пользователя',
          },
        )
        .toBe(true);

      record('Авторизация через интерфейс выполнена');
      await screenshot('02-after-login');
    };

    type CreatedCourseResponse = {
      courseId?: string;
      title?: string;
      courseDescription?: string;
    };

    let createResponse: {
      status: number;
      body: CreatedCourseResponse | null;
    } | null = null;

    page.on('request', (request) => {
      const url = new URL(request.url());

      if (
        url.origin !== new URL(apiBase).origin ||
        request.method() !== 'POST' ||
        url.pathname !== '/api/courses'
      ) {
        return;
      }

      record('Отправлен запрос создания курса', {
        hasAuthorization: Boolean(
          request.headers()['authorization'],
        ),
        body: request.postData(),
      });
    });

    page.on('response', async (response) => {
      const url = new URL(response.url());

      if (
        url.origin !== new URL(apiBase).origin ||
        response.request().method() !== 'POST' ||
        url.pathname !== '/api/courses'
      ) {
        return;
      }

      let body: CreatedCourseResponse | null = null;

      try {
        body = (await response.json()) as CreatedCourseResponse;
      } catch {
        body = null;
      }

      createResponse = {
        status: response.status(),
        body,
      };

      record('Получен ответ создания курса', {
        status: response.status(),
      });
    });

    try {
      await test.step('Авторизоваться и открыть список курсов', async () => {
        await authorize();

        await expect(pageRoot).toBeVisible({
          timeout: 20_000,
        });

        await expect(
          grid.locator('.skeleton-loader'),
        ).not.toBeVisible();

        record('Страница курсов открыта');
        await screenshot('03-initial');
      });

      await test.step('Открыть форму создания курса', async () => {
        await page
          .getByRole('button', {
            name: '+ Создать курс',
            exact: true,
          })
          .click();

        await expect(modal).toBeVisible();
        await expect(nameInput).toHaveValue('');
        await expect(descriptionInput).toHaveValue('');
        await expect(createButton).toBeEnabled();

        record('Форма создания открыта');
        await screenshot('04-modal-opened');
      });

      await test.step('Заполнить и отправить форму', async () => {
        await nameInput.fill(courseName);
        await descriptionInput.fill(courseDescription);

        await expect(nameInput).toHaveValue(courseName);
        await expect(descriptionInput).toHaveValue(
          courseDescription,
        );

        record('Форма заполнена', {
          name: courseName,
          descriptionLength: courseDescription.length,
        });

        await screenshot('05-filled');

        await createButton.click();

        await expect(modal).toBeHidden({
          timeout: 30_000,
        });

        expect(
          createResponse,
          'Должен быть получен ответ POST /api/courses',
        ).toBeTruthy();

        expect(
          createResponse.status,
          'Создание курса должно вернуть 201 Created',
        ).toBe(201);

        const createdBody = createResponse.body;

        expect(
          createdBody?.courseId,
          'API должен вернуть courseId созданного курса',
        ).toBeTruthy();

        expect(createdBody?.title).toBe(courseName);
        expect(createdBody?.courseDescription).toBe(
          courseDescription,
        );

        createdCourseId = createdBody?.courseId ?? null;

        record('Курс создан', {
          courseId: createdCourseId,
        });
      });

      await test.step('Проверить карточку созданного курса', async () => {
        const createdCard = findCreatedCourse();

        await expect(createdCard).toHaveCount(1);

        const card = createdCard.first();

        await expect(
          card.locator('.card-title'),
        ).toHaveText(courseName);

        await expect(
          card.locator('.card-description'),
        ).toHaveText(courseDescription);

        await expect(
          card.locator('.card-stats-list'),
        ).toContainText('0 материалов');

        await expect(
          card.locator('.card-stats-list'),
        ).toContainText('0 тест');

        await expect(
          card.locator('.progress-label'),
        ).toContainText('0%');

        record('Карточка созданного курса отображается');
        await screenshot('06-created-card');
      });

      await test.step('Найти созданный курс через поиск', async () => {
        await searchInput.fill(courseName);

        await expect(findCreatedCourse()).toHaveCount(1);

        await expect(
          findCreatedCourse()
            .first()
            .locator('.card-title'),
        ).toHaveText(courseName);

        record('Созданный курс найден поиском');
        await screenshot('07-search-result');
      });

      record('Тест успешно пройден');
    } catch (error) {
      record('Тест завершился ошибкой');

      try {
        await screenshot('error');
      } catch {
        record('Скриншот ошибки недоступен');
      }

      throw error;
    } finally {
      try {
        await test.step('Удалить созданный тестовый курс', async () => {
          const email = requiredEnv('TEST_USER_EMAIL');
          const password = requiredEnv('TEST_USER_PASSWORD');

          const loginResponse = await apiContext.post('/api/auth/login', {
            data: {
              email,
              password,
            },
          });

          record('Авторизация API-контекста для очистки', {
            status: loginResponse.status(),
          });

          expect(
            loginResponse.status(),
            'Не удалось авторизоваться для удаления тестового курса',
          ).toBe(200);

          const auth = await loginResponse.json();

          expect(auth.accessToken).toBeTruthy();

          const authHeaders = {
            Authorization: `Bearer ${auth.accessToken}`,
          };

          if (!createdCourseId) {
            const listResponse = await apiContext.get(
              `/api/courses?title=${encodeURIComponent(
                courseName,
              )}&page=0&size=10`,
              {
                headers: authHeaders,
              },
            );

            record('Поиск курса для очистки', {
              status: listResponse.status(),
            });

            expect(listResponse.status()).toBe(200);

            const list = await listResponse.json();

            const match = list.content?.find(
              (item: {
                courseId?: string;
                title?: string;
              }) => item.title === courseName && item.courseId,
            );

            createdCourseId = match?.courseId ?? null;
          }

          if (!createdCourseId) {
            record('Созданный курс не найден; удаление не требуется');
            return;
          }

          const deleteResponse = await apiContext.delete(
            `/api/courses/${createdCourseId}`,
            {
              headers: authHeaders,
            },
          );

          record('Удаление тестового курса', {
            courseId: createdCourseId,
            status: deleteResponse.status(),
          });

          expect(
            deleteResponse.status(),
            'Тестовый курс должен быть удалён',
          ).toBe(204);
        });
      } finally {
        await writeFile(
          path.join(screenshotsDir, `${prefix}_actions.json`),
          JSON.stringify(
            {
              test: 'TC-COURSES-CREATE-001',
              courseName,
              actions,
            },
            null,
            2,
          ),
          'utf8',
        );

        await apiContext.dispose();
      }
    }
  },
);