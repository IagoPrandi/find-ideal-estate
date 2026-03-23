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
  reporter: [["html", { open: "never" }]]
});

