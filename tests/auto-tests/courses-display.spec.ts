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

test.use({
  trace: 'off',
  video: 'off',
  screenshot: 'off',
});

test(
  'TC-COURSES-DISPLAY-001: доступность и корректное отображение курсов',
  async ({ page }, testInfo) => {
    const apiBase = requiredEnv('API_BASE_URL').replace(/\/$/, '');

    const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
    await mkdir(screenshotsDir, { recursive: true });

    const prefix = [
      new Date().toISOString().replace(/[:.]/g, '-'),
      'courses-display',
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

    const emailInput = page.locator(
      'input[type="email"], input[name="email"], input[placeholder*="mail" i]',
    );

    const passwordInput = page.locator('input[type="password"]');

    const loginButton = page.getByRole('button', {
      name: /войти|авторизоваться|log in|sign in/i,
    });

    const coursesRequests: Array<{
      method: string;
      pathname: string;
      status?: number;
      query: Record<string, string>;
    }> = [];

    const tracked = new Map<object, number>();

    page.on('request', (request) => {
      const url = new URL(request.url());

      if (
        url.origin !== new URL(apiBase).origin ||
        url.pathname !== '/api/courses'
      ) {
        return;
      }

      const query: Record<string, string> = {};
      url.searchParams.forEach((value, key) => {
        query[key] = value;
      });

      tracked.set(request, coursesRequests.length);

      coursesRequests.push({
        method: request.method(),
        pathname: url.pathname,
        query,
      });

      record('Запрос списка курсов', {
        method: request.method(),
        query,
      });
    });

    page.on('response', (response) => {
      const index = tracked.get(response.request());

      if (index === undefined) {
        return;
      }

      coursesRequests[index].status = response.status();

      record('Ответ списка курсов', {
        status: response.status(),
      });
    });

    const pageRoot = page.locator('.courses-page');
    const grid = page.locator('.courses-grid');
    const cards = grid.locator('.course-card');

    const searchInput = page.getByPlaceholder(
      'Поиск по курсам...',
      { exact: true },
    );

    const sortSelect = page.locator('.sort-select');

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

    const expectCoursesLoaded = async () => {
      await expect(pageRoot).toBeVisible();
      await expect(grid).toBeVisible();

      await expect(
        grid.locator('.skeleton-loader'),
        'Индикатор загрузки должен исчезнуть',
      ).not.toBeVisible();

      await expect(
        grid.locator('.empty-state'),
        'Не должно быть ошибки или пустого состояния',
      ).not.toBeVisible();

      await expect(cards.first()).toBeVisible();
    };

    const readProgress = async (
      card: ReturnType<typeof cards.nth>,
    ) => {
      const text = await card.locator('.progress-label').innerText();
      const value = Number(text.match(/(\d{1,3})%/)?.[1] ?? -1);

      expect(
        value,
        `Некорректное значение прогресса: ${text}`,
      ).toBeGreaterThanOrEqual(0);

      expect(value).toBeLessThanOrEqual(100);

      return value;
    };

    try {
      await test.step('Авторизоваться и открыть список курсов', async () => {
        await authorize();
        await expectCoursesLoaded();

        const firstRequest = coursesRequests[0];

        expect(
          firstRequest,
          'Должен быть выполнен запрос GET /api/courses',
        ).toBeTruthy();

        expect(firstRequest.method).toBe('GET');
        expect(firstRequest.pathname).toBe('/api/courses');
        expect(firstRequest.status).toBe(200);
        expect(firstRequest.query.page).toBe('0');
        expect(firstRequest.query.size).toBe('10');

        record('Список курсов загружен');
        await screenshot('03-initial');
      });

      await test.step('Проверить карточки курсов', async () => {
        const count = await cards.count();

        expect(
          count,
          'Должен отображаться хотя бы один курс',
        ).toBeGreaterThan(0);

        const titles: string[] = [];

        for (let index = 0; index < count; index += 1) {
          const card = cards.nth(index);
          const title = (
            await card.locator('.card-title').innerText()
          ).trim();

          expect(
            title.length,
            'Название курса не должно быть пустым',
          ).toBeGreaterThan(0);

          await expect(
            card.locator('.card-badge'),
          ).toContainText(/^\d+$/);

          await expect(
            card.locator('.card-stats-list'),
          ).toContainText(/\d+\s*материалов?/);

          await expect(
            card.locator('.card-stats-list'),
          ).toContainText(/\d+\s*тест(а|ов)?/);

          await readProgress(card);

          await expect(
            card.getByRole('button', {
              name: 'Открыть',
              exact: true,
            }),
          ).toBeVisible();

          await expect(
            card.getByRole('button', {
              name: 'Удалить',
              exact: true,
            }),
          ).toBeVisible();

          titles.push(title);
        }

        expect(
          new Set(titles).size,
          'Названия отображаемых курсов не должны дублироваться',
        ).toBe(titles.length);

        record('Карточки проверены', {
          count,
          titles,
        });

        await screenshot('04-cards');
      });

      await test.step('Проверить поиск по названию', async () => {
        const firstTitle = (
          await cards.first().locator('.card-title').innerText()
        ).trim();

        const query = firstTitle.slice(0, 3);

        await searchInput.fill(query);

        await expect
          .poll(() => coursesRequests.length)
          .toBeGreaterThan(1);

        await expect
          .poll(() => coursesRequests.at(-1)?.status)
          .toBe(200);

        const request = coursesRequests.at(-1);

        expect(request?.query.title).toBe(query);
        expect(request?.query.page).toBe('0');

        await expect(cards.first()).toBeVisible();

        const visibleTitles: string[] = [];

        for (const card of await cards.all()) {
          visibleTitles.push(
            (await card.locator('.card-title').innerText()).trim(),
          );
        }

        expect(
          visibleTitles.every((title) =>
            title.toLowerCase().includes(query.toLowerCase()),
          ),
          'Все отображённые курсы должны соответствовать запросу',
        ).toBe(true);

        record('Поиск выполнен', {
          query,
          visibleTitles,
        });

        await screenshot('05-search');
      });

      await test.step('Проверить сброс поиска', async () => {
        await searchInput.fill('');

        await expect
          .poll(() => coursesRequests.length)
          .toBeGreaterThan(2);

        await expect
          .poll(() => coursesRequests.at(-1)?.status)
          .toBe(200);

        expect(
          coursesRequests.at(-1)?.query.title,
        ).toBeUndefined();

        await expectCoursesLoaded();

        record('После очистки поиска список восстановлен');
        await screenshot('06-search-cleared');
      });

      await test.step('Проверить сортировку по прогрессу', async () => {
        await sortSelect.selectOption('progress');

        await expect
          .poll(() => coursesRequests.length)
          .toBeGreaterThan(3);

        await expect
          .poll(() => coursesRequests.at(-1)?.status)
          .toBe(200);

        await expect(cards.first()).toBeVisible();

        const progressValues: number[] = [];

        for (const card of await cards.all()) {
          progressValues.push(await readProgress(card));
        }

        expect(
          progressValues.every(
            (value, index) =>
              index === 0 || progressValues[index - 1] >= value,
          ),
          'Курсы должны быть отсортированы по убыванию прогресса',
        ).toBe(true);

        record('Сортировка по прогрессу проверена', {
          progressValues,
        });

        await screenshot('07-progress-sort');
      });

      await test.step('Проверить сортировку «Сначала новые»', async () => {
        await sortSelect.selectOption('newest');

        await expect
          .poll(() => coursesRequests.length)
          .toBeGreaterThan(4);

        await expect
          .poll(() => coursesRequests.at(-1)?.status)
          .toBe(200);

        await expectCoursesLoaded();

        record('Сортировка «Сначала новые» проверена');
        await screenshot('08-newest-sort');
      });

      await test.step('Открыть курс и вернуться к списку', async () => {
        const firstCard = cards.first();
        const courseTitle = (
          await firstCard.locator('.card-title').innerText()
        ).trim();

        await firstCard
          .getByRole('button', { name: 'Открыть', exact: true })
          .click();

        const coursePage = page.locator('.course-page');

        await expect(coursePage).toBeVisible();

        await expect(
          coursePage.getByRole('button', {
            name: '← Ко всем курсам',
            exact: true,
          }),
        ).toBeVisible();

        record('Курс открыт', { courseTitle });
        await screenshot('09-course-opened');

        await coursePage
          .getByRole('button', {
            name: '← Ко всем курсам',
            exact: true,
          })
          .click();

        await expectCoursesLoaded();

        await expect(
          cards.first().locator('.card-title'),
        ).toContainText(courseTitle);

        record('Возврат к списку выполнен');
        await screenshot('10-back-to-list');
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
      await writeFile(
        path.join(screenshotsDir, `${prefix}_actions.json`),
        JSON.stringify(
          {
            test: 'TC-COURSES-DISPLAY-001',
            actions,
            coursesRequests,
          },
          null,
          2,
        ),
        'utf8',
      );
    }
  },
);