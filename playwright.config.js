import { defineConfig } from "@playwright/test";
const port = Number(process.env.E2E_PORT || 5181);
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 2,
  reporter: "list",
  outputDir: ".runtime/frontend-e2e",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
  },
});
