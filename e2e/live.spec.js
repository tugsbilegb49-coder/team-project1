import { test, expect } from "@playwright/test";

test("real Django login → department/manager → task/quality → inactive filter → server logout", async ({
  page,
  request,
}) => {
  test.skip(
    !process.env.WORKTRACK_LIVE_E2E,
    "Run with python verify_frontend.py against an isolated database.",
  );
  await page.goto("/");
  await page
    .getByLabel("Хэрэглэгчийн нэр", { exact: true })
    .fill(process.env.E2E_USERNAME);
  await page
    .getByLabel("Нууц үг", { exact: true })
    .fill(process.env.E2E_PASSWORD);
  await page.getByRole("button", { name: "Нэвтрэх", exact: true }).click();
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.getByRole('heading',{name:'Миний өнөөдөр',exact:true})).toBeVisible();
  await page.getByLabel('Төхөөрөмжийн нэр',{exact:true}).fill('Live desktop QA');
  await page.getByRole('button',{name:'Үргэлжлүүлэх',exact:true}).click();
  await page.getByRole('checkbox').check();
  await page.getByRole('button',{name:'Үргэлжлүүлэх',exact:true}).click();
  await page.getByRole('button',{name:'Төхөөрөмж холбох',exact:true}).click();
  await page.getByRole('button',{name:'Ажил эхлүүлэх',exact:true}).click();
  await page.getByRole('button',{name:'Түр зогсоох',exact:true}).click();
  await page.getByRole('button',{name:'Ажил үргэлжлүүлэх',exact:true}).click();
  await page.getByRole('button',{name:'Ажил дуусгах',exact:true}).click();
  await expect(page.getByRole('button',{name:'Ажил эхлүүлэх',exact:true})).toBeEnabled();
  await page
    .getByRole("button", { name: "Багийн гишүүд", exact: true })
    .click();
  await page.getByLabel("Хэлтсийн нэр", { exact: true }).fill("UI Smoke Team");
  await page.getByRole("button", { name: "Хэлтэс нэмэх", exact: true }).click();
  await expect(page.getByLabel("Хэлтсийн нэр", { exact: true })).toHaveValue(
    "",
  );
  await page
    .getByLabel("Хэрэглэгчийн нэр", { exact: true })
    .fill("smoke-manager");
  await page.getByLabel("Нэр", { exact: true }).fill("Smoke Manager");
  await page
    .getByLabel("Анхны нууц үг", { exact: true })
    .fill(process.env.E2E_PASSWORD);
  await page.getByLabel("Эрх", { exact: true }).selectOption("MANAGER");
  await page
    .getByLabel("Хэлтэс (заавал)", { exact: true })
    .selectOption({ label: "UI Smoke Team" });
  await page.getByRole("button", { name: "Гишүүн нэмэх", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Smoke Manager", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Даалгавар", exact: true }).click();
  await page
    .getByLabel("Даалгаврын нэр", { exact: true })
    .fill("Real HTTP task");
  const assignee = page.getByLabel("Хариуцах гишүүн", { exact: true });
  await assignee.selectOption({ label: "Smoke Manager" });
  const managerId = await assignee.inputValue();
  await page
    .getByRole("button", { name: "+ Даалгавар нэмэх", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Real HTTP task", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Төлөв", { exact: true }).selectOption("Дууссан");
  const quality = page.getByLabel("Чанарын үнэлгээ (0–100)", { exact: true });
  await expect(quality).toBeEnabled();
  await quality.fill("88");
  await page.getByRole("button", { name: "Үнэлгээ хадгалах" }).click();
  await expect(
    page.getByRole("button", { name: "Үнэлгээ хадгалах" }),
  ).toBeDisabled();
  expect(Number(await quality.inputValue())).toBe(88);
  await page
    .getByRole("button", { name: "Багийн гишүүд", exact: true })
    .click();
  const manager = page
    .locator(".task-item")
    .filter({
      has: page.getByRole("heading", { name: "Smoke Manager", exact: true }),
    });
  await manager.getByRole("button", { name: "Идэвхгүй болгох" }).click();
  await expect(manager).toContainText("Идэвхгүй");
  await page.getByRole("button", { name: "Даалгавар", exact: true }).click();
  await expect(
    page
      .getByLabel("Хариуцах гишүүн", { exact: true })
      .locator(`option[value="${managerId}"]`),
  ).toHaveCount(0);
  const tokens = JSON.parse(
    await page.evaluate(() => sessionStorage.getItem("worktrack-auth")),
  );
  const authenticated = {Authorization: `Bearer ${tokens.access}`};
  const grant = await request.post(`${process.env.VITE_API_URL}/api/consents/grant/`, {
    headers: authenticated, data: {policy_version: "camera-presence-v1"},
  });
  expect(grant.status()).toBe(201);
  const present = await request.post(`${process.env.VITE_API_URL}/api/camera-presence/ingest/`, {
    headers: authenticated,
    data: {timestamp: new Date(Date.now()-2000).toISOString(), present: true, confidence: .83},
  });
  expect(present.status()).toBe(201);
  await page.reload();
  await page.getByRole('button',{name:'Dashboard',exact:true}).click();
  await expect(page.getByLabel("Camera presence", {exact: true})).toContainText("1 / 1");
  await expect(page.getByLabel("Camera presence", {exact: true})).toContainText("83.0%");
  const enrolled=await request.post(`${process.env.VITE_API_URL}/api/devices/enroll/`,{
    headers:authenticated,data:{name:'QA browser workstation',platform:'qa-test'},
  });
  expect(enrolled.status()).toBe(201);
  const device=await enrolled.json();
  const heartbeat=await request.post(`${process.env.VITE_API_URL}/api/agent-status/heartbeat/`,{
    headers:authenticated,data:{device_id:device.id,kind:'computer',queue_count:3,paused:false,error_code:'network'},
  });
  expect(heartbeat.status()).toBe(200);
  await page.getByRole('button',{name:'Agent төлөв',exact:true}).click();
  await expect(page.getByLabel('QA browser workstation computer',{exact:true})).toContainText('3');
  await page.getByRole('button',{name:'Өөрчлөлтийн түүх',exact:true}).click();
  await expect(page.getByText('Чанарын үнэлгээ:',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Тохиргоо',exact:true}).click();
  await page.getByLabel('Camera confidence threshold',{exact:true}).fill('0.55');
  await page.getByRole('button',{name:'Тохиргоо хадгалах',exact:true}).click();
  await expect(page.getByText('Хадгаллаа.',{exact:false})).toBeVisible();
  const settings=await request.get(`${process.env.VITE_API_URL}/api/monitoring-settings/`,{headers:authenticated});
  expect((await settings.json()).camera_threshold).toBe(.55);
  await page.getByRole('button',{name:'Тайлан',exact:true}).click();
  const fileReady=page.waitForEvent('download');
  await page.getByRole('button',{name:'Тайлан татах',exact:true}).click();
  expect((await fileReady).suggestedFilename()).toMatch(/\.csv$/);
  await page.getByRole("button", { name: "Гарах", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "WorkTrack — Нэвтрэх" }),
  ).toBeVisible();
  const revoked = await request.post(
    `${process.env.VITE_API_URL}/api/auth/refresh/`,
    { data: { refresh: tokens.refresh } },
  );
  expect(revoked.status()).toBe(401);
  await page.getByLabel('Хэрэглэгчийн нэр',{exact:true}).fill(process.env.E2E_USERNAME);
  await page.getByLabel('Нууц үг',{exact:true}).fill(process.env.E2E_PASSWORD);
  await page.getByRole('button',{name:'Нэвтрэх',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Миний өнөөдөр',exact:true})).toBeVisible();
  const previous=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('worktrack-auth')));
  await page.getByRole('button',{name:'Миний бүртгэл',exact:true}).click();
  await page.getByLabel('Одоогийн нууц үг',{exact:true}).fill(process.env.E2E_PASSWORD);
  await page.getByLabel('Шинэ нууц үг',{exact:true}).fill(process.env.E2E_PASSWORD+'-new');
  await page.getByLabel('Шинэ нууц үг давтах',{exact:true}).fill(process.env.E2E_PASSWORD+'-new');
  await page.getByRole('button',{name:'Нууц үг солих',exact:true}).click();
  await expect(page.getByRole('heading',{name:'WorkTrack — Нэвтрэх',exact:true})).toBeVisible();
  expect((await request.get(`${process.env.VITE_API_URL}/api/users/me/`,{headers:{Authorization:`Bearer ${previous.access}`}})).status()).toBe(401);
  expect((await request.post(`${process.env.VITE_API_URL}/api/auth/login/`,{data:{username:process.env.E2E_USERNAME,password:process.env.E2E_PASSWORD+'-new'}})).status()).toBe(200);
});
