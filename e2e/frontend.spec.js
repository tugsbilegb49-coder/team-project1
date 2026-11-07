import { test, expect } from '@playwright/test';

const auth = { access: 'browser-test-access', refresh: 'browser-test-refresh' };
function gate() {
  let release;
  const promise = new Promise((resolve) => {
    release = resolve;
  });
  return { promise, release };
}
async function mockApp(page) {
  const state = {
    members: [
      {
        id: 1,
        username: 'admin',
        first_name: 'Admin',
        role: 'ADMIN',
        is_admin: true,
        is_active: true,
        department: null,
      },
      {
        id: 2,
        username: 'worker',
        first_name: 'Worker',
        role: 'EMPLOYEE',
        is_active: true,
        department: 1,
      },
      {
        id: 3,
        username: 'inactive',
        first_name: 'Inactive',
        role: 'EMPLOYEE',
        is_active: false,
        department: 1,
      },
    ],
    tasks: [
      {
        id: 11,
        title: 'Existing task',
        employee: 2,
        employee_name: 'worker',
        status: 'TODO',
        quality_score: '50.00',
        due_date: null,
      },
    ],
    departments: [{ id: 1, name: 'Development' }],
    posts: [],
    desktopPosts: [],
    patches: [],
    score: '42.00',
    appName: 'Visual Studio Code',
    presence: null,
    notifications: [],
    devices: [],
    audit: [],
    settings: {
      productive_apps: ['Visual Studio Code'],
      camera_threshold: 0.45,
      presence_log_max_bytes: 5242880,
      presence_log_backups: 3,
      presence_log_retention_days: 7,
      activity_retention_days: 90,
      automatic_retention: false,
      version: 1,
    },
    desktop: {
      available: true,
      linked: false,
      reminders_enabled: true,
      reminder: null,
      another_account: false,
      computer_running: false,
      camera_running: false,
      paused: true,
      camera_ready: true,
      errors: [],
      launcher_usage: {
        available: true,
        running: true,
        current_month: '2026-11',
        as_of: Date.now() / 1000,
        month_ends_at: Date.now() / 1000 + 86400,
        recorded_since: '2026-10-01T00:00:00+08:00',
        months: [
          { month: '2026-11', seconds: 123 },
          { month: '2026-10', seconds: 90000 },
        ],
      },
    },
    workSession: null,
  };
  await page.route('**/desktop/**', (route) => {
    const action = new URL(route.request().url()).pathname.split('/')[2];
    if (route.request().method() === 'POST') state.desktopPosts.push(action);
    if (action === 'connect')
      Object.assign(state.desktop, {
        linked: true,
        username: 'admin',
        device_name: route.request().postDataJSON().device_name,
      });
    if (action === 'start') Object.assign(state.desktop, { computer_running: true, paused: false });
    if (action === 'pause') state.desktop.paused = true;
    if (action === 'resume') state.desktop.paused = false;
    if (action === 'camera-on') state.desktop.camera_running = true;
    if (action === 'camera-off') state.desktop.camera_running = false;
    if (action === 'reminders-on' || action === 'reminders-off')
      state.desktop.reminders_enabled = action === 'reminders-on';
    if (action === 'autostart-on' || action === 'autostart-off')
      state.desktop.autostart_enabled = action === 'autostart-on';
    if (action === 'stop')
      Object.assign(state.desktop, {
        computer_running: false,
        camera_running: false,
        paused: true,
      });
    return route.fulfill({ json: state.desktop });
  });
  await page.addInitScript(
    (tokens) => sessionStorage.setItem('worktrack-auth', JSON.stringify(tokens)),
    auth,
  );
  await page.route('**/api/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      method = request.method();
    const path = url.pathname;
    const data = method === 'GET' ? null : request.postDataJSON();
    const respond = (body, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    if (path === '/api/auth/logout/') {
      state.posts.push({ path, data });
      return route.fulfill({ status: 204 });
    }
    if (path === '/api/tasks/work-session/')
      return respond({ session: state.workSession, server_now: new Date().toISOString() });
    if (path === '/api/reports/monthly/')
      return respond({
        month: url.searchParams.get('month'),
        generated_at: new Date().toISOString(),
        employees: [],
      });
    const taskAction = path.match(/^\/api\/tasks\/(\d+)\/([\w-]+)\/$/);
    if (taskAction) {
      const task = state.tasks.find((row) => row.id === Number(taskAction[1]));
      const action = taskAction[2];
      if (action === 'transfer-recipients')
        return respond(
          state.members
            .filter((row) => row.is_active && row.id !== task.employee)
            .map((row) => ({ id: row.id, username: row.username, name: row.first_name })),
        );
      if (action === 'work-start') {
        state.workSession = {
          id: 81,
          task_id: task.id,
          title: task.title,
          seconds: 0,
          running: true,
          started_at: new Date().toISOString(),
          lease_expires_at: new Date(Date.now() + 90000).toISOString(),
        };
        state.posts.push({ path, data });
        return respond({ session: state.workSession, server_now: new Date().toISOString() }, 201);
      }
      if (action === 'work-stop') {
        state.workSession = null;
        state.posts.push({ path, data });
        return respond({ session: null, server_now: new Date().toISOString() });
      }
      if (action === 'progress') {
        const row = task.collaboration.contributions.find(
          (row) => row.employee === state.members[0].id,
        );
        row.percent = data.percent;
        task.collaboration.progress_percent = data.percent;
        state.posts.push({ path, data });
        return respond(task);
      }
      if (action === 'transfer-request') {
        const recipient = state.members.find((row) => row.id === data.recipient);
        task.collaboration.pending_transfer = {
          id: 91,
          from_employee: task.employee,
          from_name: task.employee_name,
          to_employee: recipient.id,
          to_name: recipient.username,
          requested_by: state.members[0].id,
          status: 'PENDING',
          note: data.note,
        };
        state.posts.push({ path, data });
        return respond(task);
      }
      if (action === 'transfer-respond') {
        const transfer = task.collaboration.pending_transfer;
        if (data.decision === 'accept') {
          task.employee = transfer.to_employee;
          task.employee_name = transfer.to_name;
          task.transfer_count = (task.transfer_count || 0) + 1;
        }
        task.collaboration.pending_transfer = null;
        state.posts.push({ path, data });
        return respond(task);
      }
    }
    if (path === '/api/notifications/')
      return respond({ items: state.notifications, count: state.notifications.length });
    if (path === '/api/agent-status/')
      return respond({
        results: state.devices,
        count: state.devices.length,
        next: null,
        previous: null,
      });
    if (path === '/api/audit/')
      return respond({
        results: state.audit,
        count: state.audit.length,
        next: null,
        previous: null,
      });
    if (path === '/api/monitoring-settings/') {
      if (method === 'PATCH') {
        state.patches.push({ path, data });
        Object.assign(state.settings, data, { version: state.settings.version + 1 });
      }
      return respond(state.settings);
    }
    if (path === '/api/reports/export/')
      return route.fulfill({
        status: 200,
        contentType: 'text/csv',
        body: 'date,username\n2026-11-05,worker\n',
      });
    if (path === '/api/auth/login/') return respond(auth);
    if (path === '/api/me/today/')
      return respond({
        date: '2026-11-06',
        tracked_seconds: 3660,
        application_seconds: 3600,
        idle_seconds: 60,
        open_tasks: 1,
        overdue_tasks: 0,
        applications: [{ application: state.appName, seconds: 3660 }],
        latest_application: { application: state.appName },
        tasks: [],
      });
    if (path === '/api/me/week/') {
      state.weekRequests = [...(state.weekRequests || []), url.searchParams.get('start') || ''];
      const start = url.searchParams.get('start') || '2026-11-02';
      const days = Array.from({ length: 7 }, (_, index) => {
        const date = new Date(Date.parse(start + 'T00:00:00Z') + index * 86400000);
        return {
          date: date.toISOString().slice(0, 10),
          task_seconds: index === 2 ? 7200 : index === 3 ? 1800 : 0,
          application_seconds: index === 2 ? 10800 : index === 3 ? 3600 : 0,
          idle_seconds: index === 2 ? 600 : 0,
        };
      });
      return respond({
        start,
        end: days[6].date,
        days,
        totals: { task_seconds: 9000, application_seconds: 14400, idle_seconds: 600 },
        tasks: [
          { id: 11, title: 'Weekly design', status: 'IN_PROGRESS', seconds: 7200 },
          { id: 12, title: 'Weekly review', status: 'DONE', seconds: 1800 },
        ],
        completed_tasks: 1,
      });
    }
    if (path === '/api/me/password/') {
      state.posts.push({ path, data });
      return respond({ detail: 'changed' });
    }
    if (path === '/api/auth/refresh/') return respond({ access: 'new-access' });
    if (path === '/api/users/me/') return respond(state.members[0]);
    if (method === 'GET' && path === '/api/users/')
      return respond({ results: state.members, next: null });
    if (method === 'GET' && path === '/api/departments/')
      return respond({ results: state.departments, next: null });
    if (method === 'GET' && path === '/api/tasks/')
      return respond({ results: state.tasks, next: null });
    if (method === 'POST' && path === '/api/users/') {
      state.posts.push({ path, data });
      const member = { ...data, id: 20, is_active: true };
      state.members.push(member);
      return respond(member, 201);
    }
    if (method === 'POST' && path === '/api/departments/') {
      state.posts.push({ path, data });
      const row = { ...data, id: 2 };
      state.departments.push(row);
      return respond(row, 201);
    }
    if (method === 'PATCH' && path.startsWith('/api/tasks/')) {
      state.patches.push({ path, data });
      Object.assign(state.tasks[0], data);
      return respond(state.tasks[0]);
    }
    if (method === 'PATCH' && /^\/api\/users\/\d+\/$/.test(path)) {
      state.patches.push({ path, data });
      const member = state.members.find((row) => row.id === Number(path.split('/')[3]));
      return respond(member);
    }
    if (path === '/api/scores/calculate/') {
      state.score = '75.00';
      return respond({}, 201);
    }
    if (path === '/api/scores/dashboard/')
      return respond({
        score: { score: state.score, category: 'LOW' },
        applications: [{ application: state.appName, category: 'WORK', seconds: 600 }],
        application_categories: [{ category: 'WORK', seconds: 600 }],
        camera: [],
        presence: state.presence,
      });
    return respond({ detail: `Unexpected request: ${method} ${path}` }, 500);
  });
  return state;
}

test('today home guides consent then controls work and camera explicitly', async ({ page }) => {
  const state = await mockApp(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Миний өнөөдөр', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '1 цаг 0 мин', exact: true })).toBeVisible();
  await page.getByLabel('Төхөөрөмжийн нэр', { exact: true }).fill('My QA Mac');
  await page.getByRole('button', { name: 'Үргэлжлүүлэх', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Үргэлжлүүлэх', exact: true })).toBeDisabled();
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Үргэлжлүүлэх', exact: true }).click();
  await page.getByRole('button', { name: 'Төхөөрөмж холбох', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true })).toBeDisabled();
  await page.getByLabel('Хийх даалгавар', { exact: true }).selectOption('none');
  await page.locator('.camera-controls summary').click();
  await expect(page.getByRole('button', { name: 'Камер асаах', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true }).click();
  expect(state.desktop.camera_running).toBe(false);
  await page.getByRole('button', { name: 'Камер асаах', exact: true }).click();
  await page.getByRole('button', { name: 'Камер унтраах', exact: true }).click();
  await page.getByRole('button', { name: 'Түр зогсоох', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Камер асаах', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Ажил үргэлжлүүлэх', exact: true }).click();
  await page.getByRole('button', { name: 'Ажил дуусгах', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true })).toBeDisabled();
  expect(state.desktop.computer_running).toBe(false);
});

test('self-service password requires matching confirmation and returns to login after save', async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Миний бүртгэл', exact: true }).click();
  await page.getByLabel('Одоогийн нууц үг', { exact: true }).fill('Old-password-948!');
  await page.getByLabel('Шинэ нууц үг', { exact: true }).fill('New-password-579!');
  await page.getByLabel('Шинэ нууц үг давтах', { exact: true }).fill('Different-password-579!');
  await page.getByRole('button', { name: 'Нууц үг солих', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('ижил');
  expect(state.posts.some((row) => row.path === '/api/me/password/')).toBe(false);
  await page.getByLabel('Шинэ нууц үг давтах', { exact: true }).fill('New-password-579!');
  await page.getByRole('button', { name: 'Нууц үг солих', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'WorkTrack — Нэвтрэх', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Нууц үг солигдлоо');
});

test('login explains how to recover a forgotten username or password', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'WorkTrack — Нэвтрэх' })).toBeVisible();
  await expect(
    page.getByText('Нэвтрэх нэр эсвэл нууц үгээ мартсан бол', { exact: false }),
  ).toContainText('админтай холбогдоно уу');
});

test('launcher monthly clock survives navigation and reload and selects historical totals', async ({
  page,
}) => {
  const state = await mockApp(page);
  state.desktop.launcher_usage.months[0].seconds = 3661;
  await page.goto('/');
  const clock = page.getByLabel('WorkTrack сарын хугацаа', { exact: true });
  await expect(clock).toContainText('01:01:01');
  const summary = page.getByRole('region', { name: 'Хугацааны тойм', exact: true });
  await expect(summary.getByLabel('WorkTrack сарын хугацаа', { exact: true })).toContainText(
    'WorkTrack хаалттай байсан хугацааг тооцохгүй',
  );
  await expect(summary.getByLabel('Өнөөдрийн аппын хэрэглээ', { exact: true })).toContainText(
    '1 цаг 0 мин',
  );
  await expect(summary.getByLabel('Өнөөдрийн аппын хэрэглээ', { exact: true })).toContainText(
    'Идэвхгүй 1 мин-ийг хассан',
  );
  await expect(clock).toHaveCount(1);
  await page.getByRole('button', { name: 'Багийн гишүүд', exact: true }).click();
  await expect(clock).toHaveCount(0);
  state.desktop.launcher_usage.months[0].seconds = 3670;
  await page.reload();
  await expect(clock).toContainText('01:01:10');
  await expect(summary).toBeVisible();
  await expect(clock).toHaveCount(1);
  await clock.getByLabel('Сар сонгох').selectOption('2026-10');
  await expect(clock).toContainText('25:00:00');
  await page.waitForTimeout(1100);
  await expect(clock).toContainText('25:00:00');
  await clock.getByLabel('Сар сонгох').selectOption('');
  await expect(clock).toContainText('01:01:');
});

test('admin finds monthly employees under reports and can inspect another month on mobile', async ({
  page,
}) => {
  await mockApp(page);
  await page.route('**/api/reports/monthly/**', (route) => {
    const month = new URL(route.request().url()).searchParams.get('month');
    return route.fulfill({
      json: {
        month,
        generated_at: new Date().toISOString(),
        employees: [
          {
            employee: 2,
            name: 'Worker',
            username: 'worker',
            department: 'Engineering',
            is_active: true,
            launcher_seconds: month === '2026-10' ? 7200 : 36000,
            launcher_recorded_since: '2026-10-01T00:00:00Z',
            launcher_last_upload: new Date().toISOString(),
            application_seconds: 18000,
            idle_seconds: 3600,
            task_seconds: 7200,
            completed_tasks: [{ id: 1, title: 'Monthly report integration' }],
            transfers_sent: 1,
            transfers_received: 2,
            tasks: [
              {
                id: 1,
                title: 'Monthly report integration',
                seconds: 7200,
                contribution_percent: '35.00',
              },
            ],
            applications: [
              { application: 'Visual Studio Code', seconds: 18000 },
              { application: 'Idle', seconds: 3600 },
            ],
          },
        ],
      },
    });
  });
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/');
  const report = page.getByRole('region', { name: 'Сарын ажилтны тайлан', exact: true });
  // "Миний өнөөдөр" keeps the admin's own work controls first; the report lives under "Тайлан".
  await expect(page.getByRole('heading', { name: 'Одоо хийх ажил', exact: true })).toBeVisible();
  await expect(report).toHaveCount(0);
  await page.getByRole('button', { name: 'Тайлан', exact: true }).click();
  await expect(report).toContainText('Worker');
  await expect(report).toContainText('10:00:00');
  await report.locator('summary').click();
  await expect(report).toContainText('35.00%');
  await expect(report).toContainText('Visual Studio Code');
  await report.getByLabel('Тайлангийн сар').fill('2026-10');
  await expect(report.locator('dl')).toContainText('02:00:00');
  await expect(report.locator('dl')).not.toContainText('10:00:00');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: '.runtime/qa/monthly-report-mobile.png', fullPage: true });
});

test('task owner records time and percent then requests a handoff without changing the owner', async ({
  page,
}) => {
  const state = await mockApp(page);
  Object.assign(state.desktop, { linked: true, username: 'admin', device_name: 'QA laptop' });
  Object.assign(state.tasks[0], {
    employee: 1,
    employee_name: 'admin',
    transfer_count: 0,
    can_manage: true,
    collaboration: {
      contributions: [
        { employee: 1, username: 'admin', percent: '0', seconds: 0, time_share_percent: 0 },
      ],
      total_seconds: 0,
      progress_percent: '0',
      transfers: [],
      pending_transfer: null,
    },
  });
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  const card = page.getByLabel('Existing task — оролцоо', { exact: true });
  await card.getByRole('button', { name: 'Энэ ажлыг сонгох', exact: true }).click();
  await expect(page.getByLabel('Хийх даалгавар', { exact: true })).toHaveValue('11');
  await page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true }).click();
  await expect(page.getByLabel('Одоогийн даалгаврын цаг', { exact: true })).toContainText(
    'Бүртгэж байна',
  );
  expect(state.desktop.computer_running).toBe(true);
  expect(state.desktop.camera_running).toBe(false);
  await page.getByRole('button', { name: 'Миний бүртгэл', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Түр зогсоох', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Ажлын удирдлагад очих', exact: true }).click();
  await page.getByRole('button', { name: 'Түр зогсоох', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ажил үргэлжлүүлэх', exact: true })).toBeEnabled();
  expect(state.workSession).toBeNull();
  expect(state.desktop.paused).toBe(true);
  await page.getByRole('button', { name: 'Ажил үргэлжлүүлэх', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Түр зогсоох', exact: true })).toBeVisible();
  expect(state.workSession.task_id).toBe(11);
  expect(state.desktop.paused).toBe(false);
  await page.getByRole('button', { name: 'Ажил дуусгах', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true })).toBeDisabled();
  expect(state.workSession).toBeNull();
  expect(state.desktop.computer_running).toBe(false);
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  await card.getByLabel('Миний хийсэн хувь', { exact: false }).fill('35');
  await card.getByRole('button', { name: 'Хувь хадгалах', exact: true }).click();
  await expect(card.getByRole('heading', { name: 'Оролцоо · нийт 35%' })).toBeVisible();
  await card.getByRole('button', { name: 'Шилжүүлэх хүсэлт', exact: true }).click();
  await card.getByLabel('Хүлээн авах гишүүн', { exact: true }).selectOption('2');
  await card
    .getByLabel('Шилжүүлэх тайлбар', { exact: true })
    .fill('Үлдсэн хэсгийг үргэлжлүүлнэ үү.');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: '.runtime/qa/task-collaboration-mobile.png', fullPage: true });
  await card.getByRole('button', { name: 'Хүсэлт илгээх', exact: true }).click();
  await expect(card).toContainText('admin → worker');
  await expect(card).toContainText('Шилжүүлсэн: 0 / 2');
  expect(state.tasks[0].employee).toBe(1);
  expect(state.posts.find((row) => row.path.endsWith('/progress/')).data).toEqual({
    percent: '35',
    expected_percent: '0',
  });
});

test('only the recipient sees acceptance controls and exhausted handoffs cannot be requested', async ({
  page,
}) => {
  const state = await mockApp(page);
  Object.assign(state.members[0], { is_admin: false, role: 'EMPLOYEE', department: 1 });
  Object.assign(state.tasks[0], {
    can_manage: false,
    transfer_count: 1,
    collaboration: {
      contributions: [],
      total_seconds: 0,
      progress_percent: 0,
      transfers: [],
      pending_transfer: {
        id: 92,
        from_employee: 2,
        to_employee: 1,
        from_name: 'worker',
        to_name: 'admin',
        requested_by: 2,
        status: 'PENDING',
        note: 'Үргэлжлүүлнэ үү.',
      },
    },
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  const card = page.getByLabel('Existing task — оролцоо', { exact: true });
  await expect(card.getByRole('button', { name: 'Энэ ажлыг сонгох', exact: true })).toHaveCount(0);
  await expect(card.getByRole('button', { name: 'Хүсэлт цуцлах', exact: true })).toHaveCount(0);
  await card.getByRole('button', { name: 'Хүлээн авах', exact: true }).click();
  await expect(card).toContainText('Шилжүүлсэн: 2 / 2');
  await expect(card.getByRole('button', { name: 'Шилжүүлэх хүсэлт', exact: true })).toHaveCount(0);
  await expect(card.getByRole('button', { name: 'Энэ ажлыг сонгох', exact: true })).toBeVisible();
});

test('admin resets the selected member password with confirmation, errors and cancel handling', async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Багийн гишүүд', exact: true }).click();
  const worker = page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: 'Worker', exact: true }) });
  await expect(worker).toContainText('Нэвтрэх нэр: worker');
  await expect(
    page
      .locator('article')
      .filter({ has: page.getByRole('heading', { name: 'Admin', exact: true }) })
      .getByRole('button', { name: 'Нууц үг шинэчлэх', exact: true }),
  ).toHaveCount(0);
  const toggle = worker.getByRole('button', { name: 'Нууц үг шинэчлэх', exact: true });
  await toggle.click();
  const form = page.getByRole('form', { name: 'Нууц үг шинэчлэх — worker', exact: true });
  const password = form.getByLabel('Шинэ нууц үг', { exact: true });
  const confirmation = form.getByLabel('Шинэ нууц үг давтах', { exact: true });
  await expect(password).toBeFocused();
  await expect(password).toHaveAttribute('type', 'password');
  await password.fill('Reset-password-921!');
  await confirmation.fill('Different-password-921!');
  await form.getByRole('button', { name: 'Шинэ нууц үг хадгалах' }).click();
  await expect(form.getByRole('alert')).toContainText('ижил');
  expect(state.patches).toHaveLength(0);
  await form.getByRole('button', { name: 'Болих', exact: true }).click();
  await expect(form).toHaveCount(0);
  await expect(toggle).toBeFocused();
  await toggle.click();
  await expect(password).toHaveValue('');
  await expect(confirmation).toHaveValue('');
  await password.fill('password');
  await confirmation.fill('password');
  await page.route(
    '**/api/users/2/',
    (route) => route.fulfill({ status: 400, json: { password: ['This password is too common.'] } }),
    { times: 1 },
  );
  await form.getByRole('button', { name: 'Шинэ нууц үг хадгалах' }).click();
  await expect(form.getByRole('alert')).toContainText('Энэ нууц үг хэт түгээмэл байна.');
  await expect(form.getByRole('alert')).toBeInViewport();
  await expect(page.getByRole('alert')).toHaveCount(1);
  await expect(page.locator('main > [role="alert"]')).toHaveCount(0);
  await expect(password).toHaveAttribute('aria-invalid', 'true');
  await expect(password).toBeFocused();
  await expect(form).toBeVisible();
  await expect(worker.getByRole('status')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await password.fill('Reset-password-921!');
  await expect(form.getByRole('alert')).toHaveCount(0);
  await confirmation.fill('Reset-password-921!');
  await form.getByRole('button', { name: 'Шинэ нууц үг хадгалах' }).click();
  await expect(worker.getByRole('status')).toContainText('Нууц үг шинэчлэгдлээ');
  await expect(form).toHaveCount(0);
  await expect(page.locator('.sidebar')).toBeVisible();
  expect(state.patches).toEqual([
    { path: '/api/users/2/', data: { password: 'Reset-password-921!' } },
  ]);
});

for (const role of ['EMPLOYEE', 'MANAGER']) {
  test(`${role} cannot see admin password reset controls`, async ({ page }) => {
    const state = await mockApp(page);
    Object.assign(state.members[0], { role, is_admin: false, department: 1 });
    await page.goto('/');
    await page.getByRole('button', { name: 'Багийн гишүүд', exact: true }).click();
    await expect(page.getByText('Нэвтрэх нэр: worker', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Нууц үг шинэчлэх', exact: true })).toHaveCount(
      0,
    );
  });
}

test('today controls fit a small screen and unavailable local service offers retry', async ({
  page,
}) => {
  const state = await mockApp(page);
  state.appName = 'LongApplicationName'.repeat(12);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Миний өнөөдөр', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.route('**/desktop/**', (route) =>
    route.fulfill({ status: 503, json: { detail: 'Unavailable' } }),
  );
  await page.reload();
  await expect(page.getByRole('button', { name: 'Дахин холбогдох', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText(
    process.platform === 'win32' ? 'Start WorkTrack.bat' : 'WorkTrack.app',
  );
});

test('camera permission failures explain the Windows privacy setting', async ({ page }) => {
  const state = await mockApp(page);
  Object.assign(state.desktop, {
    platform: 'Windows',
    linked: true,
    username: 'admin',
    device_name: 'QA PC',
    errors: ['camera'],
    camera_error: 'permission',
  });
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText(
    'Windows Settings → Privacy & security → Camera',
  );
});

test('camera permission failures explain the macOS setting', async ({ page }) => {
  const state = await mockApp(page);
  Object.assign(state.desktop, {
    linked: true,
    username: 'admin',
    device_name: 'QA Mac',
    errors: ['camera'],
    camera_error: 'permission',
  });
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText(
    'System Settings → Privacy & Security → Camera → WorkTrack Camera',
  );
  await page.locator('.camera-controls summary').click();
  await expect(page.getByRole('button', { name: 'Камер асаах', exact: true })).toBeDisabled();
});

test('failed app start stops the newly created task timer and leaves an actionable inline error', async ({
  page,
}) => {
  const state = await mockApp(page);
  Object.assign(state.desktop, { linked: true, username: 'admin', device_name: 'QA laptop' });
  state.tasks[0].employee = 1;
  await page.route('**/desktop/start/', (route) =>
    route.fulfill({ status: 403, json: { detail: 'Зөвшөөрлөө дахин шалгана уу.' } }),
  );
  await page.goto('/');
  await page.getByLabel('Хийх даалгавар', { exact: true }).selectOption('11');
  await page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true }).click();
  const panel = page.getByRole('region', { name: 'Энэ компьютерийн удирдлага', exact: true });
  await expect(panel.getByRole('alert')).toContainText('даалгаврын цагийг зогсоолоо');
  expect(state.workSession).toBeNull();
  expect(state.desktop.computer_running).toBe(false);
  expect(state.posts.map((row) => row.path)).toEqual([
    '/api/tasks/11/work-start/',
    '/api/tasks/11/work-stop/',
  ]);
  await expect(panel.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true })).toBeEnabled();
});

test('a rejected task cannot start application collection', async ({ page }) => {
  const state = await mockApp(page);
  Object.assign(state.desktop, { linked: true, username: 'admin', device_name: 'QA laptop' });
  state.tasks[0].employee = 1;
  await page.route('**/api/tasks/11/work-start/', (route) =>
    route.fulfill({ status: 409, json: { detail: 'Даалгавар шилжсэн байна.' } }),
  );
  await page.goto('/');
  await page.getByLabel('Хийх даалгавар', { exact: true }).selectOption('11');
  await page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true }).click();
  await expect(
    page
      .getByRole('region', { name: 'Энэ компьютерийн удирдлага', exact: true })
      .getByRole('alert'),
  ).toContainText('Даалгавар шилжсэн');
  expect(state.desktopPosts).not.toContain('start');
  expect(state.workSession).toBeNull();
});

test('partial stop reports the failure and retry stops both streams', async ({ page }) => {
  const state = await mockApp(page);
  Object.assign(state.desktop, { linked: true, username: 'admin', device_name: 'QA laptop' });
  state.tasks[0].employee = 1;
  await page.goto('/');
  await page.getByLabel('Хийх даалгавар', { exact: true }).selectOption('11');
  await page.getByRole('button', { name: 'Ажил эхлүүлэх', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Түр зогсоох', exact: true })).toBeVisible();
  await page.route('**/desktop/stop/', (route) =>
    route.fulfill({ status: 503, json: { detail: 'Offline' } }),
  );
  await page.getByRole('button', { name: 'Ажил дуусгах', exact: true }).click();
  const panel = page.getByRole('region', { name: 'Энэ компьютерийн удирдлага', exact: true });
  await expect(panel.getByRole('alert')).toContainText(
    'Аппын бүртгэл зогссоныг баталгаажуулж чадсангүй',
  );
  expect(state.workSession).toBeNull();
  expect(state.desktop.computer_running).toBe(true);
  await page.unroute('**/desktop/stop/');
  await page.getByRole('button', { name: 'Ажил дуусгах', exact: true }).click();
  // Alert нь дахин оролдох үед шууд арилдаг тул stop дууссаныг амжилтын мессежээр хүлээнэ.
  await expect(panel.getByRole('status')).toContainText('аппын бүртгэлийг зогсоолоо');
  await expect(panel.getByRole('alert')).toHaveCount(0);
  expect(state.desktop.computer_running).toBe(false);
});

test('agent status, notifications and audit history are connected', async ({ page }) => {
  const errors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  const state = await mockApp(page);
  state.notifications = [{ id: 'offline-1', kind: 'agent_offline', message: 'QA Laptop' }];
  state.devices = [
    {
      id: 'device-1',
      name: 'QA Laptop',
      employee_name: 'worker',
      platform: 'macOS',
      enabled: true,
      agents: [
        {
          kind: 'computer',
          state: 'offline',
          queue_count: 7,
          seen_at: '2026-11-05T02:00:00Z',
          last_upload_at: null,
          error_code: 'network',
          agent_version: '0.3.0',
          settings_version: 2,
        },
      ],
    },
  ];
  state.audit = [
    {
      id: 1,
      actor_label: 'admin',
      resource: 'task',
      object_id: '11',
      action: 'update',
      created_at: '2026-11-05T02:00:00Z',
      changes: { quality_score: { before: '50.00', after: '80.00' } },
    },
  ];
  await page.goto('/');
  await page.getByText('Мэдэгдэл (1)', { exact: true }).click();
  await expect(page.getByText('Төхөөрөмж холболтгүй: QA Laptop')).toBeVisible();
  await page.getByRole('button', { name: 'Харах', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Төхөөрөмжийн төлөв', exact: true }),
  ).toBeVisible();
  const device = page.getByLabel('QA Laptop computer', { exact: true });
  await expect(device).toContainText('Холболтгүй');
  await expect(device).toContainText('7');
  await page.getByRole('button', { name: 'Өөрчлөлтийн түүх', exact: true }).click();
  await expect(page.getByText('Чанарын үнэлгээ: "50.00" → "80.00"')).toBeVisible();
  expect(errors).toEqual([]);
});

test('admin settings save with a version and export downloads the chosen date range', async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Тохиргоо', exact: true }).click();
  await page.getByLabel('Камерын итгэлцлийн босго', { exact: true }).fill('0.65');
  await page.getByRole('button', { name: 'Тохиргоо хадгалах', exact: true }).click();
  await expect(page.getByText('Хадгаллаа.', { exact: false })).toBeVisible();
  const saved = state.patches.find((row) => row.path === '/api/monitoring-settings/').data;
  expect(saved.expected_version).toBe(1);
  expect(saved.camera_threshold).toBe(0.65);
  expect(saved.automatic_retention).toBe(false);
  await page.getByRole('button', { name: 'Тайлан', exact: true }).click();
  await page.getByLabel('Эхлэх өдөр', { exact: true }).fill('2026-11-01');
  await page.getByLabel('Дуусах өдөр', { exact: true }).fill('2026-11-05');
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Тайлан татах', exact: true }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe('worktrack-2026-11-01-2026-11-05.csv');
});

test('camera presence observations appear without being shown as worked minutes', async ({
  page,
}) => {
  const state = await mockApp(page);
  state.presence = {
    samples: 5,
    present_samples: 3,
    absent_samples: 2,
    latest_present: false,
    latest_confidence: 0,
    present_percent: 60,
  };
  await page.goto('/');
  await page.getByRole('button', { name: 'Ерөнхий тойм', exact: true }).click();
  const presence = page.getByLabel('Камерын илрүүлэлт', { exact: true });
  await expect(presence).toBeVisible();
  await expect(presence).toContainText('3 / 5');
  await expect(presence).toContainText('Хүн илрээгүй');
  await expect(presence).toContainText('0.0%');
  await expect(presence).toContainText('ажилласан минутыг илэрхийлэхгүй');
  state.presence = {
    samples: 1,
    present_samples: 1,
    absent_samples: 0,
    latest_present: true,
    latest_confidence: 0.81,
    present_percent: 100,
  };
  await page.reload();
  await page.getByRole('button', { name: 'Ерөнхий тойм', exact: true }).click();
  await expect(presence).toContainText('1 / 1');
  await expect(presence).toContainText('81.0%');
});

test('saving an existing task preserves an unfinished creation draft', async ({ page }) => {
  const state = await mockApp(page),
    pending = gate();
  await page.route('**/api/tasks/11/', async (route) => {
    await pending.promise;
    await route.fallback();
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  const title = page.getByLabel('Даалгаврын нэр', { exact: true });
  await title.fill('Keep this draft');
  await page.getByLabel('Төлөв', { exact: true }).selectOption('Хийгдэж байна');
  await expect(title).toBeDisabled();
  await expect(title).toHaveValue('Keep this draft');
  pending.release();
  await expect(title).toBeEnabled();
  await expect(title).toHaveValue('Keep this draft');
  expect(state.patches[0].data.status).toBe('IN_PROGRESS');
});

test('quality validation shows an error and requires an explicit successful save', async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  const quality = page.getByLabel('Чанарын үнэлгээ (0–100)', { exact: true });
  await quality.fill('150');
  await quality.blur();
  await expect(page.getByRole('alert')).toContainText('0–100');
  await page.getByRole('button', { name: 'Үнэлгээ хадгалах' }).click();
  expect(state.patches).toHaveLength(0);
  await quality.fill('75.50');
  await page.getByRole('button', { name: 'Үнэлгээ хадгалах' }).click();
  await expect(quality).toHaveValue('75.5');
  expect(state.patches[0].data.quality_score).toBe(75.5);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('inactive members cannot be selected for a new task', async ({ page }) => {
  await mockApp(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  const assignee = page.getByLabel('Хариуцах гишүүн', { exact: true });
  await expect(assignee.locator('option[value="2"]')).toHaveCount(1);
  await expect(assignee.locator('option[value="3"]')).toHaveCount(0);
});

test('manager creation requires and submits a department', async ({ page }) => {
  const state = await mockApp(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Багийн гишүүд', exact: true }).click();
  await page.getByLabel('Хэрэглэгчийн нэр', { exact: true }).fill('new-manager');
  await page.getByLabel('Нэр', { exact: true }).fill('Manager');
  await page.getByLabel('Анхны нууц үг', { exact: true }).fill('Some-long-manager-password-2026');
  await page.getByLabel('Эрх', { exact: true }).selectOption('MANAGER');
  await page.getByRole('button', { name: 'Гишүүн нэмэх', exact: true }).click();
  expect(state.posts.filter((row) => row.path === '/api/users/')).toHaveLength(0);
  await page.getByLabel('Хэлтэс (заавал)', { exact: true }).selectOption('1');
  await page.getByRole('button', { name: 'Гишүүн нэмэх', exact: true }).click();
  await expect(page.getByLabel('Хэрэглэгчийн нэр', { exact: true })).toHaveValue('');
  const saved = state.posts.find((row) => row.path === '/api/users/').data;
  expect(saved.role).toBe('MANAGER');
  expect(saved.department).toBe(1);
});

test('report selection hides old data immediately and ignores a late response', async ({
  page,
}) => {
  await mockApp(page);
  const delayed = gate();
  await page.route('**/api/scores/dashboard/**', async (route) => {
    if (new URL(route.request().url()).searchParams.get('employee_id') === '2') {
      await delayed.promise;
      await route
        .fulfill({
          json: {
            score: { score: '12.00', category: 'LOW' },
            applications: [],
            camera: [],
          },
        })
        .catch(() => {});
    } else await route.fallback();
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Ерөнхий тойм', exact: true }).click();
  await expect(page.locator('.activity-score-card h3')).toHaveText('42.00');
  await page.getByLabel('Тайлангийн ажилтан').selectOption('2');
  await expect(page.locator('.activity-score-card')).toHaveCount(0);
  await expect(page.getByRole('status')).toContainText('Тайлан уншиж');
  await page.getByLabel('Тайлангийн ажилтан').selectOption('3');
  await expect(page.locator('.activity-score-card h3')).toHaveText('42.00');
  delayed.release();
  await expect(page.locator('.activity-score-card h3')).toHaveText('42.00');
});

test('logout revokes the server session and a late report cannot restore the UI', async ({
  page,
}) => {
  const state = await mockApp(page),
    delayed = gate();
  await page.route('**/api/scores/dashboard/**', async (route) => {
    await delayed.promise;
    await route.fallback().catch(() => {});
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Гарах', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'WorkTrack — Нэвтрэх' })).toBeVisible();
  expect(state.posts.find((row) => row.path === '/api/auth/logout/').data.refresh).toBe(
    auth.refresh,
  );
  delayed.release();
  await expect(page.locator('.sidebar')).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem('worktrack-auth'))).toBeNull();
});

test('startup backend outage preserves login and supports retry', async ({ page }) => {
  await mockApp(page);
  let unavailable = true;
  await page.route('**/api/users/me/', (route) =>
    unavailable
      ? route.fulfill({ status: 503, json: { detail: 'Temporarily offline' } })
      : route.fallback(),
  );
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Дахин холбогдох' })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('worktrack-auth'))).not.toBeNull();
  unavailable = false;
  await page.getByRole('button', { name: 'Дахин холбогдох' }).click();
  await expect(page.locator('.sidebar')).toBeVisible();
});

test('failed server logout keeps the current session for retry', async ({ page }) => {
  await mockApp(page);
  let unavailable = true;
  await page.route('**/api/auth/logout/', (route) =>
    unavailable
      ? route.fulfill({ status: 503, json: { detail: 'Logout unavailable' } })
      : route.fallback(),
  );
  await page.goto('/');
  await page.getByRole('button', { name: 'Гарах', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Logout unavailable');
  await expect(page.locator('.sidebar')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('worktrack-auth'))).not.toBeNull();
  unavailable = false;
  await page.getByRole('button', { name: 'Гарах', exact: true }).click();
  await expect(page.locator('.sidebar')).toHaveCount(0);
});

test('invalid refresh returns the user to login instead of leaving a stale dashboard', async ({
  page,
}) => {
  await mockApp(page);
  await page.route('**/api/users/me/', (route) =>
    route.fulfill({ status: 401, json: { detail: 'Expired' } }),
  );
  await page.route('**/api/auth/refresh/', (route) =>
    route.fulfill({ status: 401, json: { detail: 'Expired refresh' } }),
  );
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'WorkTrack — Нэвтрэх' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Нэвтрэх хугацаа дууссан');
  expect(await page.evaluate(() => sessionStorage.getItem('worktrack-auth'))).toBeNull();
});

test('activity charts fit a 320px viewport with long application names', async ({ page }) => {
  const state = await mockApp(page);
  state.appName = 'VeryLongApplicationName'.repeat(8);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Ерөнхий тойм', exact: true }).click();
  await expect(page.locator('.activity-score-card')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test('an incomplete numeric quality value cannot clear a saved grade', async ({ page }) => {
  const state = await mockApp(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Даалгавар', exact: true }).click();
  const quality = page.getByLabel('Чанарын үнэлгээ (0–100)', { exact: true });
  await quality.fill('');
  await quality.press('e');
  await quality.blur();
  await expect(page.getByRole('alert')).toContainText('Тоон үнэлгээ');
  await page.getByRole('button', { name: 'Үнэлгээ хадгалах' }).click();
  expect(state.patches).toHaveLength(0);
});

test('first run creates the administrator in the browser and signs straight in', async ({
  page,
}) => {
  await mockApp(page);
  await page.addInitScript(() => sessionStorage.removeItem('worktrack-auth'));
  const created = [];
  await page.route('**/api/setup/', (route) => {
    if (route.request().method() !== 'POST')
      return route.fulfill({ json: { needs_admin: true, setup_available: true } });
    const body = route.request().postDataJSON();
    created.push(body);
    if (body.password === 'password')
      return route.fulfill({
        status: 400,
        json: { password: ['This password is too common.'] },
      });
    return route.fulfill({
      status: 201,
      json: { detail: 'Админ үүслээ.', username: body.username },
    });
  });
  await page.goto('/#setup=one-time-token_123');
  await expect(page.getByRole('heading', { name: 'WorkTrack — Анхны тохиргоо' })).toBeVisible();
  await page.getByLabel('Админы нэвтрэх нэр', { exact: true }).fill('admin');
  await page.getByLabel('Нууц үг', { exact: true }).fill('password');
  await page.getByLabel('Нууц үг давтах', { exact: true }).fill('password');
  await page.getByRole('button', { name: 'Админ үүсгээд нэвтрэх', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('хэт түгээмэл');
  await page.getByLabel('Нууц үг', { exact: true }).fill('Ulaanbaatar-2026!');
  await page.getByLabel('Нууц үг давтах', { exact: true }).fill('Ulaanbaatar-2026!');
  await page.getByRole('button', { name: 'Админ үүсгээд нэвтрэх', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Миний өнөөдөр', exact: true })).toBeVisible();
  expect(created.at(-1)).toMatchObject({ token: 'one-time-token_123', username: 'admin' });
  expect(new URL(page.url()).hash).toBe(''); // The secret does not stay in the address bar.
});

test('login page explains how to create the first administrator', async ({ page }) => {
  await mockApp(page);
  await page.addInitScript(() => sessionStorage.removeItem('worktrack-auth'));
  await page.route('**/api/setup/', (route) =>
    route.fulfill({ json: { needs_admin: true, setup_available: false } }),
  );
  await page.goto('/');
  await expect(page.getByText('Админ хараахан үүсээгүй байна.')).toBeVisible();
});

test('my week shows time per day and per task and moves between weeks', async ({ page }) => {
  const state = await mockApp(page);
  await page.goto('/');
  const week = page.getByRole('region', { name: 'Миний 7 хоног', exact: true });
  await expect(week).toContainText('11/02 – 11/08');
  await expect(week).toContainText('Даалгаварт 2 цаг 30 мин');
  await expect(
    week.getByLabel('Даваа 11/02: даалгаварт 0 сек, компьютер дээр 0 сек'),
  ).toContainText('Бүртгэлгүй');
  await expect(
    week.getByLabel('Лхагва 11/04: даалгаварт 2 цаг 0 мин, компьютер дээр 3 цаг 0 мин'),
  ).toBeVisible();
  await expect(week).toContainText('Weekly design');
  await expect(week.getByRole('button', { name: 'Дараах ›' })).toBeDisabled();
  await week.getByRole('button', { name: '‹ Өмнөх' }).click();
  await expect(week).toContainText('10/26 – 11/01');
  await week.getByRole('button', { name: 'Дараах ›' }).click();
  await expect(week).toContainText('11/02 – 11/08');
  expect(state.weekRequests).toEqual(expect.arrayContaining(['', '2026-10-26']));
});

test('a reminder shows on the page and reminders can be turned off', async ({ page }) => {
  const state = await mockApp(page);
  Object.assign(state.desktop, {
    linked: true,
    username: 'admin',
    device_name: 'QA laptop',
    reminder: 'Ажил эхлүүлэхээ мартсан уу? WorkTrack дээр «Ажил эхлүүлэх» дарна уу.',
  });
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Энэ компьютерийн удирдлага', exact: true });
  await expect(panel.getByRole('status')).toContainText('Ажил эхлүүлэхээ мартсан уу?');
  await panel.getByText('Төхөөрөмжийн нэмэлт үйлдэл').click();
  await panel.getByRole('button', { name: 'Сануулга унтраах', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Сануулга асаах', exact: true })).toBeVisible();
  expect(state.desktop.reminders_enabled).toBe(false);
});

test('starting at sign-in is explained before linking and can be switched off', async ({
  page,
}) => {
  const state = await mockApp(page);
  Object.assign(state.desktop, {
    autostart_supported: true,
    autostart_enabled: false,
    autostart_on_connect: true,
  });
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Энэ компьютерийн удирдлага', exact: true });
  await panel.getByRole('button', { name: 'Үргэлжлүүлэх' }).click();
  await expect(panel.getByText('компьютер асахад WorkTrack далд асна')).toBeVisible();
  const toggle = panel.getByRole('checkbox', {
    name: 'Компьютер асахад WorkTrack-ийг автоматаар асаах',
  });
  // The box follows the computer's answer, so it changes after the click is saved.
  await toggle.click();
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  expect(state.desktopPosts).toEqual(['autostart-on', 'autostart-off']);
});
