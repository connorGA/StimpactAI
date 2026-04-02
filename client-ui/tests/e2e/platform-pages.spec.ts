import { test, expect, type Page } from "@playwright/test";

async function loginToWorkspace(page: Page) {
  await page.goto("/login?next=/onboarding");
  await page.getByLabel(/Work email/i).fill("connor@example.com");
  await page.getByLabel(/^Password$/i).fill("test-password");
  await page.getByRole("button", { name: /Log in to live workspace/i }).click();
}

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
  await loginToWorkspace(page);

  await expect(page.getByRole("heading", { name: /Set up your project in one guided flow/i })).toBeVisible();
  await expect(page.getByText(/Detected from the connected repo/i)).toBeVisible();
  await expect(page.getByText(/package\.json scripts in apps\/web/i)).toBeVisible();
  await expect(
    page.getByText(/Saved repo profile values are shown below\. Compare them against fresh suggestions/i),
  ).toBeVisible();
  await expect(page.getByLabel(/Verify command/i)).toHaveValue("pytest");
  await expect(page.getByLabel(/Install command/i)).toHaveValue("pip install -r requirements.txt");
  await expect(
    page.getByText(/Fresh repo suggestion: pnpm --dir apps\/web run test/i),
  ).toBeVisible();
  await expect(
    page.getByText(/Fresh repo suggestion: pnpm install --frozen-lockfile/i),
  ).toBeVisible();
});

test("onboarding automatic sdk setup requests plan and preview", async ({ page }) => {
  await loginToWorkspace(page);

  await page.locator("#onboarding-step-6").scrollIntoViewIfNeeded();
  await page.waitForTimeout(750);

  const startAutomaticAttempt = page.getByRole("button", { name: /Start automatic attempt/i });
  await startAutomaticAttempt.scrollIntoViewIfNeeded();
  await expect(startAutomaticAttempt).toBeVisible();
  await expect(page.getByText(/^Idle$/)).toBeVisible();

  const planResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" &&
    response.url().includes("/api/onboarding/projects/project-1/sdk-bootstrap/plan") &&
    response.status() === 200,
  );
  const previewResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" &&
    response.url().includes("/api/onboarding/projects/project-1/sdk-bootstrap/preview") &&
    response.status() === 200,
  );

  await startAutomaticAttempt.click();

  await planResponsePromise;
  await previewResponsePromise;

  await expect(page.getByText(/^Ready for review$/).first()).toBeVisible();
  await expect(
    page.getByText(/Multiple plausible SDK surfaces were detected\. Review the selected strategy/i),
  ).toBeVisible();
  await expect(page.getByText(/Selected strategy review/i)).toBeVisible();
  await expect(page.getByText(/Patch verification/i)).toBeVisible();
  await expect(page.getByText(/Verification passed/i)).toBeVisible();
  await expect(page.getByText(/Attempt history/i)).toBeVisible();
  await expect(page.getByText(/Tried 2 candidate surfaces before selecting the best available result\./i)).toBeVisible();
  await expect(page.getByText(/high confidence/i).first()).toBeVisible();
  await expect(page.getByText(/Add Stimpact SDK bootstrap/i)).toBeVisible();
  await expect(page.getByText("stimpact/sdk-bootstrap-preview", { exact: true })).toBeVisible();
});

test("onboarding manual sdk setup shows exact guided instructions", async ({ page }) => {
  await loginToWorkspace(page);

  await page.locator("#onboarding-step-6").scrollIntoViewIfNeeded();
  await page.waitForTimeout(750);

  const startAutomaticAttempt = page.getByRole("button", { name: /Start automatic attempt/i });
  const planResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" &&
    response.url().includes("/api/onboarding/projects/project-1/sdk-bootstrap/plan") &&
    response.status() === 200,
  );
  await startAutomaticAttempt.click();
  await planResponsePromise;

  await page.getByRole("button", { name: /Manual installation mode/i }).click();

  await expect(page.getByText(/Do these in order/i)).toBeVisible();
  await expect(page.getByText("Install the SDK dependency", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Add the required environment variables", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Wire the SDK into apps\/web\/src\/app\/layout\.tsx/i).first()).toBeVisible();
  await expect(page.getByText("Verify the first heartbeat", { exact: true }).first()).toBeVisible();
});
