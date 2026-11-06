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
  await page.getByRole("button", { name: "Гарах", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "WorkTrack — Нэвтрэх" }),
  ).toBeVisible();
  const revoked = await request.post(
    `${process.env.VITE_API_URL}/api/auth/refresh/`,
    { data: { refresh: tokens.refresh } },
  );
  expect(revoked.status()).toBe(401);
});
