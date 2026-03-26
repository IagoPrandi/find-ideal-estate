import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.BASE_URL || "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 10_000
  },
  use: {
    baseURL,
    viewport: { width: 1366, height: 768 },
    trace: "on-first-retry",
    browserName: "chromium"
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5173",
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000
  },
  reporter: [["html", { open: "never" }]]
});

