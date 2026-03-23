import { test, expect } from "@playwright/test";

test("control center shows live project policy", async ({ page }) => {
  await page.goto("/control-center");

  await expect(page.getByRole("heading", { name: /Autonomy policy, guardrails, and project access/i })).toBeVisible();
  await expect(page.getByText(/Live control-plane state for project-1/i)).toBeVisible();
  await expect(page.getByText(/Project API keys/i)).toBeVisible();
});

test("operations page shows active response data", async ({ page }) => {
  await page.goto("/operations");

  await expect(page.getByRole("heading", { name: /Run the active response workflow from one place/i })).toBeVisible();
  await expect(page.getByText(/Autonomous repair is actively working this incident/i)).toBeVisible();
});

test("automations page shows live execution history", async ({ page }) => {
  await page.goto("/automations");

  await expect(page.getByRole("heading", { name: /Automation catalog and recent remediation activity/i })).toBeVisible();
  await expect(page.getByText(/available/i).first()).toBeVisible();
  await expect(page.getByText(/Latest autonomous run is running in phase verification/i)).toBeVisible();
});

test("metrics page shows automation health module", async ({ page }) => {
  await page.goto("/metrics");

  await expect(page.getByRole("heading", { name: /Reliability reporting built around trend reading and operational signal/i })).toBeVisible();
  await expect(page.getByText(/Automation health/i)).toBeVisible();
  await expect(page.getByText(/Backend readiness/i)).toBeVisible();
});

test("onboarding page supports project setup workflow", async ({ page }) => {
  await page.goto("/onboarding");

  await expect(
    page.getByRole("heading", {
      name: /Connect a project, store secrets securely, and prepare sandbox execution/i,
    }),
  ).toBeVisible();

  await page.getByRole("button", { name: /Bootstrap/i }).click();
  await expect(page.getByText(/Project onboarding state loaded/i)).toBeVisible();

  await page.getByRole("button", { name: /Connect GitHub/i }).click();
  await expect(page.getByText(/GitHub integration connected/i)).toBeVisible();

  await page.getByLabel(/Secret value/i).fill("super-secret-value");
  await page.getByRole("button", { name: /Store secret/i }).click();
  await expect(page.getByText(/Secret stored in AWS Secrets Manager/i)).toBeVisible();

  await page.getByRole("button", { name: /Sync repos/i }).first().click();
  await expect(page.getByText(/Provider repositories synced/i)).toBeVisible();

  await page.getByRole("button", { name: /Create repo profile/i }).click();
  await expect(page.getByText(/Repo profile created/i)).toBeVisible();
});
