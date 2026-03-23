import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "node tests/mock-agent-platform.mjs",
      port: 4010,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 3100",
      port: 3100,
      reuseExistingServer: !process.env.CI,
      env: {
        ...process.env,
        AGENT_PLATFORM_API_URL: "http://127.0.0.1:4010",
      },
    },
  ],
});
