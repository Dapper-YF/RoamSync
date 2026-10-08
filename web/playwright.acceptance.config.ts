import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "demo-*.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 900_000,
  outputDir: "../backend/evals/results/demo_acceptance_20261007/browser",
  reporter: [["list"], ["json", { outputFile: "../backend/evals/results/demo_acceptance_20261007/playwright.json" }]],
  use: {
    baseURL: "http://127.0.0.1:3001",
    channel: "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 1000 },
  },
});
