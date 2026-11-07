import { test, expect } from '@playwright/test';

test('real Django login → department/manager → task/quality → inactive filter → server logout', async ({
  page,
  request,
  browser,
}) => {
  test.skip(
    !process.env.WORKTRACK_LIVE_E2E,
    'Run with python verify_frontend.py against an isolated database.',
  );
  test.setTimeout(90000);
  await page.goto('/');
  await page.getByLabel('Хэрэглэгчийн нэр', { exact: true }).fill(process.env.E2E_USERNAME);
  await page.getByLabel('Нууц үг', { exact: true }).fill(process.env.E2E_PASSWORD);
  await page.getByRole('button', { name: 'Нэвтрэх', exact: true }).click();
  await expect(page.locator('.sidebar')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Миний өнөөдөр', exact: true })).toBeVisible();
  await page.getByLabel('Төхөөрөмжийн нэр', { exact: true }).fill('Live desktop QA');
  await page.getByRole('button', { name: 'Үргэлжлүүлэх', exact: true }).click();
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Үргэлжлүүлэх', exact: true }).click();
  await page.getByRole('button', { name: 'Төхөөрөмж холбох', exact: true }).click();
  const workflowTokens = await page.evaluate(() =>
    JSON.parse(sessionStorage.getItem('worktrack-auth')),
  );
  const workflowHeaders = { Authorization: `Bearer ${workflowTokens.access}` };
  const workflowUser = await (
    await request.get(`${process.env.VITE_API_URL}/api/users/me/`, { headers: workflowHeaders })
  ).json();
  const workflowCreated = await request.post(`${process.env.VITE_API_URL}/api/tasks/`, {
    headers: workflowHeaders,
    data: { title: 'Unified workday QA', employee: workflowUser.id },
  });
  expect(workflowCreated.status()).toBe(201);
  const workflowTask = await workflowCreated.json();
  await page.reload();
  await page.getByLabel('Хийх даалгавар', { exact: true }).selectOption(String(workflowTask.id));
  await page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true }).click();
  await expect(page.getByLabel('Одоогийн даалгаврын цаг', { exact: true })).toContainText(
    'Бүртгэж байна',
  );
  await page.getByRole('button', { name: 'Түр зогсоох', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ажил үргэлжлүүлэх', exact: true })).toBeEnabled();
  expect(
    (
      await (
        await request.get(`${process.env.VITE_API_URL}/api/tasks/work-session/`, {
          headers: workflowHeaders,
        })
      ).json()
    ).session,
  ).toBeNull();
  await page.getByRole('button', { name: 'Ажил үргэлжлүүлэх', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Түр зогсоох', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Ажил дуусгах', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true })).toBeDisabled();
  expect(
    (
      await (
        await request.get(`${process.env.VITE_API_URL}/api/tasks/work-session/`, {
          headers: workflowHeaders,
        })
      ).json()
    ).session,
  ).toBeNull();
  expect(
    (
      await request.delete(`${process.env.VITE_API_URL}/api/tasks/${workflowTask.id}/`, {
        headers: workflowHeaders,
      })
    ).status(),
  ).toBe(204);
  await page.getByRole('button', { name: 'Багийн гишүүд', exact: true }).click();
  await page.getByLabel('Хэлтсийн нэр', { exact: true }).fill('UI Smoke Team');
  await page.getByRole('button', { name: 'Хэлтэс нэмэх', exact: true }).click();
  await expect(page.getByLabel('Хэлтсийн нэр', { exact: true })).toHaveValue('');
  await page.getByLabel('Хэрэглэгчийн нэр', { exact: true }).fill('smoke-manager');
  await page.getByLabel('Нэр', { exact: true }).fill('Smoke Manager');
  await page.getByLabel('Анхны нууц үг', { exact: true }).fill(process.env.E2E_PASSWORD);
  await page.getByLabel('Эрх', { exact: true }).selectOption('MANAGER');
  await page
    .getByLabel('Хэлтэс (заавал)', { exact: true })
    .selectOption({ label: 'UI Smoke Team' });
  await page.getByRole('button', { name: 'Гишүүн нэмэх', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Smoke Manager', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  await page.getByLabel('Даалгаврын нэр', { exact: true }).fill('Real HTTP task');
  const assignee = page.getByLabel('Хариуцах гишүүн', { exact: true });
  await assignee.selectOption({ label: 'Smoke Manager' });
  const managerId = await assignee.inputValue();
  await page.getByRole('button', { name: '+ Даалгавар нэмэх', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Real HTTP task', exact: true })).toBeVisible();
  await page.getByLabel('Төлөв', { exact: true }).selectOption('Дууссан');
  const quality = page.getByLabel('Чанарын үнэлгээ (0–100)', { exact: true });
  await expect(quality).toBeEnabled();
  await quality.fill('88');
  await page.getByRole('button', { name: 'Үнэлгээ хадгалах' }).click();
  await expect(page.getByRole('button', { name: 'Үнэлгээ хадгалах' })).toBeDisabled();
  expect(Number(await quality.inputValue())).toBe(88);
  await page.getByRole('button', { name: 'Багийн гишүүд', exact: true }).click();
  const manager = page.locator('.task-item').filter({
    has: page.getByRole('heading', { name: 'Smoke Manager', exact: true }),
  });
  await expect(manager).toContainText('Нэвтрэх нэр: smoke-manager');
  const oldLogin = await request.post(`${process.env.VITE_API_URL}/api/auth/login/`, {
    data: { username: 'smoke-manager', password: process.env.E2E_PASSWORD },
  });
  expect(oldLogin.status()).toBe(200);
  const oldSession = await oldLogin.json();
  await manager.getByRole('button', { name: 'Нууц үг шинэчлэх', exact: true }).click();
  await manager.getByLabel('Шинэ нууц үг', { exact: true }).fill('password');
  await manager.getByLabel('Шинэ нууц үг давтах', { exact: true }).fill('password');
  await manager.getByRole('button', { name: 'Шинэ нууц үг хадгалах', exact: true }).click();
  await expect(manager.getByRole('alert')).toContainText('Энэ нууц үг хэт түгээмэл байна.');
  await expect(page.locator('main > [role="alert"]')).toHaveCount(0);
  await manager
    .getByLabel('Шинэ нууц үг', { exact: true })
    .fill(process.env.E2E_PASSWORD + '-reset');
  await manager
    .getByLabel('Шинэ нууц үг давтах', { exact: true })
    .fill(process.env.E2E_PASSWORD + '-reset');
  await manager.getByRole('button', { name: 'Шинэ нууц үг хадгалах', exact: true }).click();
  await expect(manager.getByRole('status')).toContainText('Нууц үг шинэчлэгдлээ');
  expect(
    (
      await request.get(`${process.env.VITE_API_URL}/api/users/me/`, {
        headers: { Authorization: `Bearer ${oldSession.access}` },
      })
    ).status(),
  ).toBe(401);
  expect(
    (
      await request.post(`${process.env.VITE_API_URL}/api/auth/refresh/`, {
        data: { refresh: oldSession.refresh },
      })
    ).status(),
  ).toBe(401);
  expect(
    (
      await request.post(`${process.env.VITE_API_URL}/api/auth/login/`, {
        data: { username: 'smoke-manager', password: process.env.E2E_PASSWORD + '-reset' },
      })
    ).status(),
  ).toBe(200);
  await manager.getByRole('button', { name: 'Идэвхгүй болгох' }).click();
  await expect(manager).toContainText('Идэвхгүй');
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  await expect(
    page.getByLabel('Хариуцах гишүүн', { exact: true }).locator(`option[value="${managerId}"]`),
  ).toHaveCount(0);
  const tokens = JSON.parse(await page.evaluate(() => sessionStorage.getItem('worktrack-auth')));
  const authenticated = { Authorization: `Bearer ${tokens.access}` };
  const grant = await request.post(`${process.env.VITE_API_URL}/api/consents/grant/`, {
    headers: authenticated,
    data: { policy_version: 'camera-presence-v1' },
  });
  expect(grant.status()).toBe(201);
  const present = await request.post(`${process.env.VITE_API_URL}/api/camera-presence/ingest/`, {
    headers: authenticated,
    data: { timestamp: new Date(Date.now() - 2000).toISOString(), present: true, confidence: 0.83 },
  });
  expect(present.status()).toBe(201);
  await page.reload();
  await page.getByRole('button', { name: 'Ерөнхий тойм', exact: true }).click();
  await expect(page.getByLabel('Camera presence', { exact: true })).toContainText('1 / 1');
  await expect(page.getByLabel('Camera presence', { exact: true })).toContainText('83.0%');
  const enrolled = await request.post(`${process.env.VITE_API_URL}/api/devices/enroll/`, {
    headers: authenticated,
    data: { name: 'QA browser workstation', platform: 'qa-test' },
  });
  expect(enrolled.status()).toBe(201);
  const device = await enrolled.json();
  const heartbeat = await request.post(`${process.env.VITE_API_URL}/api/agent-status/heartbeat/`, {
    headers: authenticated,
    data: {
      device_id: device.id,
      kind: 'computer',
      queue_count: 3,
      paused: false,
      error_code: 'network',
    },
  });
  expect(heartbeat.status()).toBe(200);
  await page.getByRole('button', { name: 'Төхөөрөмжийн төлөв', exact: true }).click();
  await expect(page.getByLabel('QA browser workstation computer', { exact: true })).toContainText(
    '3',
  );
  await page.getByRole('button', { name: 'Өөрчлөлтийн түүх', exact: true }).click();
  await expect(page.getByText('Чанарын үнэлгээ:', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Тохиргоо', exact: true }).click();
  await page.getByLabel('Camera confidence threshold', { exact: true }).fill('0.55');
  await page.getByRole('button', { name: 'Тохиргоо хадгалах', exact: true }).click();
  await expect(page.getByText('Хадгаллаа.', { exact: false })).toBeVisible();
  const settings = await request.get(`${process.env.VITE_API_URL}/api/monitoring-settings/`, {
    headers: authenticated,
  });
  expect((await settings.json()).camera_threshold).toBe(0.55);
  await page.getByRole('button', { name: 'Тайлан', exact: true }).click();
  const fileReady = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Тайлан татах', exact: true }).click();
  expect((await fileReady).suggestedFilename()).toMatch(/\.csv$/);
  await exerciseTaskHandoff({ page, request, browser, headers: authenticated });
  // The real desktop bridge checkpoints and uploads without browser writes.
  await expect
    .poll(
      async () => {
        const response = await request.get(`${process.env.VITE_API_URL}/api/reports/monthly/`, {
          headers: authenticated,
        });
        expect(response.status()).toBe(200);
        const data = await response.json();
        return (
          data.employees.find((row) => row.username === process.env.E2E_USERNAME)
            ?.launcher_seconds || 0
        );
      },
      { timeout: 40000, intervals: [1000] },
    )
    .toBeGreaterThan(0);
  await page.getByRole('button', { name: 'Тайлан', exact: true }).click();
  const monthly = page.getByRole('region', { name: 'Сарын ажилтны тайлан', exact: true });
  await monthly.getByRole('button', { name: 'Сарын тайлан шинэчлэх', exact: true }).click();
  await expect(monthly).toContainText('handoff-first');
  await expect(monthly).toContainText('Програмын цаг илгээсэн:');
  await page.getByRole('button', { name: 'Гарах', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'WorkTrack — Нэвтрэх' })).toBeVisible();
  const revoked = await request.post(`${process.env.VITE_API_URL}/api/auth/refresh/`, {
    data: { refresh: tokens.refresh },
  });
  expect(revoked.status()).toBe(401);
  await page.getByLabel('Хэрэглэгчийн нэр', { exact: true }).fill(process.env.E2E_USERNAME);
  await page.getByLabel('Нууц үг', { exact: true }).fill(process.env.E2E_PASSWORD);
  await page.getByRole('button', { name: 'Нэвтрэх', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Миний өнөөдөр', exact: true })).toBeVisible();
  const previous = await page.evaluate(() => JSON.parse(sessionStorage.getItem('worktrack-auth')));
  await page.getByRole('button', { name: 'Миний бүртгэл', exact: true }).click();
  await page.getByLabel('Одоогийн нууц үг', { exact: true }).fill(process.env.E2E_PASSWORD);
  await page.getByLabel('Шинэ нууц үг', { exact: true }).fill(process.env.E2E_PASSWORD + '-new');
  await page
    .getByLabel('Шинэ нууц үг давтах', { exact: true })
    .fill(process.env.E2E_PASSWORD + '-new');
  await page.getByRole('button', { name: 'Нууц үг солих', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'WorkTrack — Нэвтрэх', exact: true }),
  ).toBeVisible();
  expect(
    (
      await request.get(`${process.env.VITE_API_URL}/api/users/me/`, {
        headers: { Authorization: `Bearer ${previous.access}` },
      })
    ).status(),
  ).toBe(401);
  expect(
    (
      await request.post(`${process.env.VITE_API_URL}/api/auth/login/`, {
        data: { username: process.env.E2E_USERNAME, password: process.env.E2E_PASSWORD + '-new' },
      })
    ).status(),
  ).toBe(200);
});

async function exerciseTaskHandoff({ page, request, browser, headers }) {
  const api = process.env.VITE_API_URL;
  const departments = await (await request.get(`${api}/api/departments/`, { headers })).json();
  const department = departments.results.find((row) => row.name === 'UI Smoke Team').id;
  const people = [],
    contexts = [];
  try {
    for (const name of ['first', 'second', 'third']) {
      const created = await request.post(`${api}/api/users/`, {
        headers,
        data: {
          username: `handoff-${name}`,
          first_name: name,
          password: process.env.E2E_PASSWORD,
          department,
          role: 'EMPLOYEE',
        },
      });
      expect(created.status()).toBe(201);
      const user = await created.json();
      const login = await request.post(`${api}/api/auth/login/`, {
        data: { username: user.username, password: process.env.E2E_PASSWORD },
      });
      expect(login.status()).toBe(200);
      const tokens = await login.json();
      const context = await browser.newContext();
      contexts.push(context);
      await context.addInitScript(
        (value) => sessionStorage.setItem('worktrack-auth', JSON.stringify(value)),
        tokens,
      );
      const tab = await context.newPage();
      people.push({ user, tab, headers: { Authorization: `Bearer ${tokens.access}` } });
    }
    const [first, second, third] = people;
    const created = await request.post(`${api}/api/tasks/`, {
      headers,
      data: { title: 'Shared live handoff', employee: first.user.id },
    });
    expect(created.status()).toBe(201);
    const task = await created.json();
    for (const person of people) {
      await person.tab.goto(new URL('/', page.url()).href);
      await person.tab.getByRole('button', { name: 'Даалгавар', exact: true }).click();
    }
    const card = (person) =>
      person.tab.getByLabel('Shared live handoff — оролцоо', { exact: true });
    await card(first).getByText('Аппын бүртгэлгүй ажиллах', { exact: true }).click();
    await card(first)
      .getByRole('button', { name: 'Зөвхөн даалгаврын цаг эхлүүлэх', exact: true })
      .click();
    await expect(first.tab.getByRole('button', { name: 'Түр зогсоох', exact: true })).toBeVisible();
    await card(first).getByLabel('Миний хийсэн хувь', { exact: false }).fill('35');
    await card(first).getByRole('button', { name: 'Хувь хадгалах', exact: true }).click();
    await expect(card(first)).toContainText('Хийсэн хувь: 35%');
    async function handoff(sender, receiver) {
      await card(sender).getByRole('button', { name: 'Шилжүүлэх хүсэлт', exact: true }).click();
      await card(sender)
        .getByLabel('Хүлээн авах гишүүн', { exact: true })
        .selectOption(String(receiver.user.id));
      await card(sender)
        .getByLabel('Шилжүүлэх тайлбар', { exact: true })
        .fill('Live handoff evidence');
      await card(sender).getByRole('button', { name: 'Хүсэлт илгээх', exact: true }).click();
      await expect(card(sender)).toContainText('Хариу хүлээж байна');
      const before = await (await request.get(`${api}/api/tasks/${task.id}/`, { headers })).json();
      expect(before.employee).toBe(sender.user.id);
      await receiver.tab.getByRole('button', { name: 'Даалгавар шинэчлэх', exact: true }).click();
      await card(receiver).getByRole('button', { name: 'Хүлээн авах', exact: true }).click();
      await expect(
        card(receiver).getByRole('button', { name: 'Энэ ажлыг сонгох', exact: true }),
      ).toBeVisible();
    }
    await handoff(first, second);
    expect(
      (
        await request
          .get(`${api}/api/tasks/work-session/`, { headers: first.headers })
          .then((r) => r.json())
      ).session,
    ).toBeNull();
    await card(second).getByText('Аппын бүртгэлгүй ажиллах', { exact: true }).click();
    await card(second)
      .getByRole('button', { name: 'Зөвхөн даалгаврын цаг эхлүүлэх', exact: true })
      .click();
    await card(second).getByLabel('Миний хийсэн хувь', { exact: false }).fill('40');
    await card(second).getByRole('button', { name: 'Хувь хадгалах', exact: true }).click();
    await expect(card(second)).toContainText('Хийсэн хувь: 40%');
    await handoff(second, third);
    await card(third).getByLabel('Миний хийсэн хувь', { exact: false }).fill('25');
    await card(third).getByRole('button', { name: 'Хувь хадгалах', exact: true }).click();
    await expect(card(third)).toContainText('Оролцоо · нийт 100%');
    await expect(card(third)).toContainText('Шилжүүлсэн: 2 / 2');
    await expect(
      card(third).getByRole('button', { name: 'Шилжүүлэх хүсэлт', exact: true }),
    ).toHaveCount(0);
    const result = await (await request.get(`${api}/api/tasks/${task.id}/`, { headers })).json();
    expect(result.employee).toBe(third.user.id);
    expect(result.collaboration.contributions.map((row) => Number(row.percent))).toEqual([
      35, 40, 25,
    ]);
    expect(result.collaboration.total_seconds).toBeGreaterThanOrEqual(0);
    expect(result.collaboration.transfers.filter((row) => row.status === 'ACCEPTED')).toHaveLength(
      2,
    );
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
}
