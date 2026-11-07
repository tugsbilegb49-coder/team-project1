import { test, expect } from "@playwright/test";

const auth = { access: "browser-test-access", refresh: "browser-test-refresh" };
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
        username: "admin",
        first_name: "Admin",
        role: "ADMIN",
        is_admin: true,
        is_active: true,
        department: null,
      },
      {
        id: 2,
        username: "worker",
        first_name: "Worker",
        role: "EMPLOYEE",
        is_active: true,
        department: 1,
      },
      {
        id: 3,
        username: "inactive",
        first_name: "Inactive",
        role: "EMPLOYEE",
        is_active: false,
        department: 1,
      },
    ],
    tasks: [
      {
        id: 11,
        title: "Existing task",
        employee: 2,
        employee_name: "worker",
        status: "TODO",
        quality_score: "50.00",
        due_date: null,
      },
    ],
    departments: [{ id: 1, name: "Development" }],
    posts: [],
    patches: [],
    score: "42.00",
    appName: "Visual Studio Code",
    presence: null,
    notifications: [],
    devices: [],
    audit: [],
    settings: {productive_apps:['Visual Studio Code'],camera_threshold:.45,presence_log_max_bytes:5242880,
      presence_log_backups:3,presence_log_retention_days:7,activity_retention_days:90,automatic_retention:false,version:1},
    desktop: {available:true,linked:false,another_account:false,computer_running:false,camera_running:false,paused:true,camera_ready:true,errors:[]},
  };
  await page.route('**/desktop/**',route=>{
    const action=new URL(route.request().url()).pathname.split('/')[2];
    if(action==='connect')Object.assign(state.desktop,{linked:true,username:'admin',device_name:route.request().postDataJSON().device_name});
    if(action==='start')Object.assign(state.desktop,{computer_running:true,paused:false});
    if(action==='pause')state.desktop.paused=true;
    if(action==='resume')state.desktop.paused=false;
    if(action==='camera-on')state.desktop.camera_running=true;
    if(action==='camera-off')state.desktop.camera_running=false;
    if(action==='stop')Object.assign(state.desktop,{computer_running:false,camera_running:false,paused:true});
    return route.fulfill({json:state.desktop});
  });
  await page.addInitScript(
    (tokens) =>
      sessionStorage.setItem("worktrack-auth", JSON.stringify(tokens)),
    auth,
  );
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      method = request.method();
    const path = url.pathname;
    const data = method === "GET" ? null : request.postDataJSON();
    const respond = (body, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (path === "/api/auth/logout/") {
      state.posts.push({ path, data });
      return route.fulfill({ status: 204 });
    }
    if (path === '/api/notifications/') return respond({items:state.notifications,count:state.notifications.length});
    if (path === '/api/agent-status/') return respond({results:state.devices,count:state.devices.length,next:null,previous:null});
    if (path === '/api/audit/') return respond({results:state.audit,count:state.audit.length,next:null,previous:null});
    if (path === '/api/monitoring-settings/') {
      if (method === 'PATCH') {state.patches.push({path,data});Object.assign(state.settings,data,{version:state.settings.version+1});}
      return respond(state.settings);
    }
    if (path === '/api/reports/export/') return route.fulfill({status:200,contentType:'text/csv',body:'date,username\n2026-11-05,worker\n'});
    if (path === "/api/auth/login/") return respond(auth);
    if(path==='/api/me/today/')return respond({date:'2026-11-06',tracked_seconds:3660,open_tasks:1,overdue_tasks:0,
      applications:[{application:state.appName,seconds:3660}],latest_application:{application:state.appName},tasks:[]});
    if(path==='/api/me/password/'){state.posts.push({path,data});return respond({detail:'changed'});}
    if (path === "/api/auth/refresh/") return respond({ access: "new-access" });
    if (path === "/api/users/me/") return respond(state.members[0]);
    if (method === "GET" && path === "/api/users/")
      return respond({ results: state.members, next: null });
    if (method === "GET" && path === "/api/departments/")
      return respond({ results: state.departments, next: null });
    if (method === "GET" && path === "/api/tasks/")
      return respond({ results: state.tasks, next: null });
    if (method === "POST" && path === "/api/users/") {
      state.posts.push({ path, data });
      const member = { ...data, id: 20, is_active: true };
      state.members.push(member);
      return respond(member, 201);
    }
    if (method === "POST" && path === "/api/departments/") {
      state.posts.push({ path, data });
      const row = { ...data, id: 2 };
      state.departments.push(row);
      return respond(row, 201);
    }
    if (method === "PATCH" && path.startsWith("/api/tasks/")) {
      state.patches.push({ path, data });
      Object.assign(state.tasks[0], data);
      return respond(state.tasks[0]);
    }
    if (path === "/api/scores/calculate/") {
      state.score = "75.00";
      return respond({}, 201);
    }
    if (path === "/api/scores/dashboard/")
      return respond({
        score: { score: state.score, category: "LOW" },
        applications: [
          { application: state.appName, category: "WORK", seconds: 600 },
        ],
        application_categories: [{ category: "WORK", seconds: 600 }],
        camera: [],
        presence: state.presence,
      });
    return respond({ detail: `Unexpected request: ${method} ${path}` }, 500);
  });
  return state;
}

test('today home guides consent then controls work and camera explicitly',async({page})=>{
  const state=await mockApp(page);await page.goto('/');
  await expect(page.getByRole('heading',{name:'Миний өнөөдөр',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'1 цаг 1 мин',exact:true})).toBeVisible();
  await page.getByLabel('Төхөөрөмжийн нэр',{exact:true}).fill('My QA Mac');
  await page.getByRole('button',{name:'Үргэлжлүүлэх',exact:true}).click();
  await expect(page.getByRole('button',{name:'Үргэлжлүүлэх',exact:true})).toBeDisabled();
  await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Үргэлжлүүлэх',exact:true}).click();
  await page.getByRole('button',{name:'Төхөөрөмж холбох',exact:true}).click();
  await expect(page.getByRole('button',{name:'Camera асаах',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Ажил эхлүүлэх',exact:true}).click();
  expect(state.desktop.camera_running).toBe(false);
  await page.getByRole('button',{name:'Camera асаах',exact:true}).click();
  await page.getByRole('button',{name:'Camera унтраах',exact:true}).click();
  await page.getByRole('button',{name:'Түр зогсоох',exact:true}).click();
  await expect(page.getByRole('button',{name:'Camera асаах',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Ажил үргэлжлүүлэх',exact:true}).click();
  await page.getByRole('button',{name:'Ажил дуусгах',exact:true}).click();
  await expect(page.getByRole('button',{name:'Ажил эхлүүлэх',exact:true})).toBeEnabled();
  expect(state.desktop.computer_running).toBe(false);
});

test('self-service password requires matching confirmation and returns to login after save',async({page})=>{
  const state=await mockApp(page);await page.goto('/');
  await page.getByRole('button',{name:'Миний бүртгэл',exact:true}).click();
  await page.getByLabel('Одоогийн нууц үг',{exact:true}).fill('Old-password-948!');
  await page.getByLabel('Шинэ нууц үг',{exact:true}).fill('New-password-579!');
  await page.getByLabel('Шинэ нууц үг давтах',{exact:true}).fill('Different-password-579!');
  await page.getByRole('button',{name:'Нууц үг солих',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('ижил');
  expect(state.posts.some(row=>row.path==='/api/me/password/')).toBe(false);
  await page.getByLabel('Шинэ нууц үг давтах',{exact:true}).fill('New-password-579!');
  await page.getByRole('button',{name:'Нууц үг солих',exact:true}).click();
  await expect(page.getByRole('heading',{name:'WorkTrack — Нэвтрэх',exact:true})).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Нууц үг солигдлоо');
});

test('today controls fit a small screen and unavailable local service offers retry',async({page})=>{
  const state=await mockApp(page);state.appName='LongApplicationName'.repeat(12);
  await page.setViewportSize({width:320,height:800});await page.goto('/');
  await expect(page.getByRole('heading',{name:'Миний өнөөдөр',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.route('**/desktop/**',route=>route.fulfill({status:503,json:{detail:'Unavailable'}}));
  await page.reload();
  await expect(page.getByRole('button',{name:'Дахин холбогдох',exact:true})).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('WorkTrack.app');
});

test('agent status, notifications and audit history are connected', async ({page}) => {
  const errors=[];page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  const state=await mockApp(page);
  state.notifications=[{id:'offline-1',kind:'agent_offline',message:'QA Laptop'}];
  state.devices=[{id:'device-1',name:'QA Laptop',employee_name:'worker',platform:'macOS',enabled:true,agents:[
    {kind:'computer',state:'offline',queue_count:7,seen_at:'2026-11-05T02:00:00Z',last_upload_at:null,error_code:'network',agent_version:'0.3.0',settings_version:2}]}];
  state.audit=[{id:1,actor_label:'admin',resource:'task',object_id:'11',action:'update',created_at:'2026-11-05T02:00:00Z',changes:{quality_score:{before:'50.00',after:'80.00'}}}];
  await page.goto('/');
  await page.getByText('Мэдэгдэл (1)',{exact:true}).click();
  await expect(page.getByText('Agent холболтгүй: QA Laptop')).toBeVisible();
  await page.getByRole('button',{name:'Харах',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Agent-ийн төлөв',exact:true})).toBeVisible();
  const device=page.getByLabel('QA Laptop computer',{exact:true});
  await expect(device).toContainText('Холболтгүй');
  await expect(device).toContainText('7');
  await page.getByRole('button',{name:'Өөрчлөлтийн түүх',exact:true}).click();
  await expect(page.getByText('Чанарын үнэлгээ: "50.00" → "80.00"')).toBeVisible();
  expect(errors).toEqual([]);
});

test('admin settings save with a version and export downloads the chosen date range', async ({page}) => {
  const state=await mockApp(page);
  await page.goto('/');
  await page.getByRole('button',{name:'Тохиргоо',exact:true}).click();
  await page.getByLabel('Camera confidence threshold',{exact:true}).fill('0.65');
  await page.getByRole('button',{name:'Тохиргоо хадгалах',exact:true}).click();
  await expect(page.getByText('Хадгаллаа.',{exact:false})).toBeVisible();
  const saved=state.patches.find(row=>row.path==='/api/monitoring-settings/').data;
  expect(saved.expected_version).toBe(1);expect(saved.camera_threshold).toBe(.65);
  expect(saved.automatic_retention).toBe(false);
  await page.getByRole('button',{name:'Тайлан',exact:true}).click();
  await page.getByLabel('Эхлэх өдөр',{exact:true}).fill('2026-11-01');
  await page.getByLabel('Дуусах өдөр',{exact:true}).fill('2026-11-05');
  const downloading=page.waitForEvent('download');
  await page.getByRole('button',{name:'Тайлан татах',exact:true}).click();
  const download=await downloading;
  expect(download.suggestedFilename()).toBe('worktrack-2026-11-01-2026-11-05.csv');
});

test("camera presence observations appear without being shown as worked minutes", async ({page}) => {
  const state = await mockApp(page);
  state.presence = {samples: 5, present_samples: 3, absent_samples: 2,
    latest_present: false, latest_confidence: 0, present_percent: 60};
  await page.goto("/");
  await page.getByRole("button", {name:"Dashboard",exact:true}).click();
  const presence = page.getByLabel("Camera presence", {exact: true});
  await expect(presence).toBeVisible();
  await expect(presence).toContainText("3 / 5");
  await expect(presence).toContainText("Хүн илрээгүй");
  await expect(presence).toContainText("0.0%");
  await expect(presence).toContainText("ажилласан минутыг илэрхийлэхгүй");
  state.presence = {samples: 1, present_samples: 1, absent_samples: 0,
    latest_present: true, latest_confidence: .81, present_percent: 100};
  await page.reload();
  await page.getByRole('button',{name:'Dashboard',exact:true}).click();
  await expect(presence).toContainText("1 / 1");
  await expect(presence).toContainText("81.0%");
});

test("saving an existing task preserves an unfinished creation draft", async ({
  page,
}) => {
  const state = await mockApp(page),
    pending = gate();
  await page.route("**/api/tasks/11/", async (route) => {
    await pending.promise;
    await route.fallback();
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Даалгавар", exact: true }).click();
  const title = page.getByLabel("Даалгаврын нэр", { exact: true });
  await title.fill("Keep this draft");
  await page.getByLabel("Төлөв", { exact: true }).selectOption("Хийгдэж байна");
  await expect(title).toBeDisabled();
  await expect(title).toHaveValue("Keep this draft");
  pending.release();
  await expect(title).toBeEnabled();
  await expect(title).toHaveValue("Keep this draft");
  expect(state.patches[0].data.status).toBe("IN_PROGRESS");
});

test("quality validation shows an error and requires an explicit successful save", async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Даалгавар", exact: true }).click();
  const quality = page.getByLabel("Чанарын үнэлгээ (0–100)", { exact: true });
  await quality.fill("150");
  await quality.blur();
  await expect(page.getByRole("alert")).toContainText("0–100");
  await page.getByRole("button", { name: "Үнэлгээ хадгалах" }).click();
  expect(state.patches).toHaveLength(0);
  await quality.fill("75.50");
  await page.getByRole("button", { name: "Үнэлгээ хадгалах" }).click();
  await expect(quality).toHaveValue("75.5");
  expect(state.patches[0].data.quality_score).toBe(75.5);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("inactive members cannot be selected for a new task", async ({ page }) => {
  await mockApp(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Даалгавар", exact: true }).click();
  const assignee = page.getByLabel("Хариуцах гишүүн", { exact: true });
  await expect(assignee.locator('option[value="2"]')).toHaveCount(1);
  await expect(assignee.locator('option[value="3"]')).toHaveCount(0);
});

test("manager creation requires and submits a department", async ({ page }) => {
  const state = await mockApp(page);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Багийн гишүүд", exact: true })
    .click();
  await page
    .getByLabel("Хэрэглэгчийн нэр", { exact: true })
    .fill("new-manager");
  await page.getByLabel("Нэр", { exact: true }).fill("Manager");
  await page
    .getByLabel("Анхны нууц үг", { exact: true })
    .fill("Some-long-manager-password-2026");
  await page.getByLabel("Эрх", { exact: true }).selectOption("MANAGER");
  await page.getByRole("button", { name: "Гишүүн нэмэх", exact: true }).click();
  expect(state.posts.filter((row) => row.path === "/api/users/")).toHaveLength(
    0,
  );
  await page.getByLabel("Хэлтэс (заавал)", { exact: true }).selectOption("1");
  await page.getByRole("button", { name: "Гишүүн нэмэх", exact: true }).click();
  await expect(
    page.getByLabel("Хэрэглэгчийн нэр", { exact: true }),
  ).toHaveValue("");
  const saved = state.posts.find((row) => row.path === "/api/users/").data;
  expect(saved.role).toBe("MANAGER");
  expect(saved.department).toBe(1);
});

test("report selection hides old data immediately and ignores a late response", async ({
  page,
}) => {
  await mockApp(page);
  const delayed = gate();
  await page.route("**/api/scores/dashboard/**", async (route) => {
    if (
      new URL(route.request().url()).searchParams.get("employee_id") === "2"
    ) {
      await delayed.promise;
      await route
        .fulfill({
          json: {
            score: { score: "12.00", category: "LOW" },
            applications: [],
            camera: [],
          },
        })
        .catch(() => {});
    } else await route.fallback();
  });
  await page.goto("/");
  await page.getByRole("button", {name:"Dashboard",exact:true}).click();
  await expect(page.locator(".activity-score-card h3")).toHaveText("42.00");
  await page.getByLabel("Тайлангийн ажилтан").selectOption("2");
  await expect(page.locator(".activity-score-card")).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText("Тайлан уншиж");
  await page.getByLabel("Тайлангийн ажилтан").selectOption("3");
  await expect(page.locator(".activity-score-card h3")).toHaveText("42.00");
  delayed.release();
  await expect(page.locator(".activity-score-card h3")).toHaveText("42.00");
});

test("logout revokes the server session and a late report cannot restore the UI", async ({
  page,
}) => {
  const state = await mockApp(page),
    delayed = gate();
  await page.route("**/api/scores/dashboard/**", async (route) => {
    await delayed.promise;
    await route.fallback().catch(() => {});
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Гарах", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "WorkTrack — Нэвтрэх" }),
  ).toBeVisible();
  expect(
    state.posts.find((row) => row.path === "/api/auth/logout/").data.refresh,
  ).toBe(auth.refresh);
  delayed.release();
  await expect(page.locator(".sidebar")).toHaveCount(0);
  expect(
    await page.evaluate(() => sessionStorage.getItem("worktrack-auth")),
  ).toBeNull();
});

test("startup backend outage preserves login and supports retry", async ({
  page,
}) => {
  await mockApp(page);
  let unavailable = true;
  await page.route("**/api/users/me/", (route) =>
    unavailable
      ? route.fulfill({ status: 503, json: { detail: "Temporarily offline" } })
      : route.fallback(),
  );
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Дахин холбогдох" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("worktrack-auth")),
  ).not.toBeNull();
  unavailable = false;
  await page.getByRole("button", { name: "Дахин холбогдох" }).click();
  await expect(page.locator(".sidebar")).toBeVisible();
});

test("failed server logout keeps the current session for retry", async ({
  page,
}) => {
  await mockApp(page);
  let unavailable = true;
  await page.route("**/api/auth/logout/", (route) =>
    unavailable
      ? route.fulfill({ status: 503, json: { detail: "Logout unavailable" } })
      : route.fallback(),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Гарах", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Logout unavailable");
  await expect(page.locator(".sidebar")).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("worktrack-auth")),
  ).not.toBeNull();
  unavailable = false;
  await page.getByRole("button", { name: "Гарах", exact: true }).click();
  await expect(page.locator(".sidebar")).toHaveCount(0);
});

test("invalid refresh returns the user to login instead of leaving a stale dashboard", async ({
  page,
}) => {
  await mockApp(page);
  await page.route("**/api/users/me/", (route) =>
    route.fulfill({ status: 401, json: { detail: "Expired" } }),
  );
  await page.route("**/api/auth/refresh/", (route) =>
    route.fulfill({ status: 401, json: { detail: "Expired refresh" } }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "WorkTrack — Нэвтрэх" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "Нэвтрэх хугацаа дууссан",
  );
  expect(
    await page.evaluate(() => sessionStorage.getItem("worktrack-auth")),
  ).toBeNull();
});

test("activity charts fit a 320px viewport with long application names", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.appName = "VeryLongApplicationName".repeat(8);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/");
  await page.getByRole("button", {name:"Dashboard",exact:true}).click();
  await expect(page.locator(".activity-score-card")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("an incomplete numeric quality value cannot clear a saved grade", async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Даалгавар", exact: true }).click();
  const quality = page.getByLabel("Чанарын үнэлгээ (0–100)", { exact: true });
  await quality.fill("");
  await quality.press("e");
  await quality.blur();
  await expect(page.getByRole("alert")).toContainText("Тоон үнэлгээ");
  await page.getByRole("button", { name: "Үнэлгээ хадгалах" }).click();
  expect(state.patches).toHaveLength(0);
});
