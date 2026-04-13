import http from "node:http";
import { SignJWT } from "jose";

const incident = {
  id: "incident-1",
  project_id: "project-1",
  fingerprint: "fingerprint-1",
  service: "billing-api",
  environment: "production",
  title: "billing-api: Database timeout",
  status: "open",
  severity: "high",
  first_seen_at: "2026-03-20T12:00:00Z",
  last_seen_at: "2026-03-20T12:05:00Z",
  event_count: 3,
  latest_telemetry_id: "telemetry-1",
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:05:00Z",
};

const autonomousRun = {
  id: "run-1",
  incident_id: "incident-1",
  async_job_id: "job-1",
  repo_profile_id: "profile-1",
  patch_run_id: "patch-1",
  sandbox_run_id: "sandbox-1",
  promotion_branch_name: null,
  promotion_url: null,
  repository_root: "/tmp/repo",
  objective: "Repair the billing timeout incident.",
  status: "running",
  phase: "verification",
  execution_mode: "repair_and_propose",
  approval_status: "pending",
  promotion_status: "not_requested",
  initializer_session_id: null,
  coding_session_id: null,
  last_error: null,
  policy: {
    auto_run_allowed: true,
    requires_human_approval: true,
    allow_writeback: false,
    allowed_execution_backends: ["kubernetes"],
    allowed_tool_categories: ["search", "edit", "verify"],
    require_browser_verification: true,
    max_repair_attempts: 3,
    max_retry_budget: 2,
    reasons: ["Human approval required before promotion."],
  },
  loop_state: {
    step_index: 4,
    max_steps: 12,
    checkpoint_ref: null,
    recovery_attempts: 0,
    consecutive_failures: 0,
    last_tool_name: "run_tests",
    recent_tool_names: ["search_code", "edit_file", "run_tests"],
    last_tool_ok: true,
    last_tool_result: {},
  },
  created_at: "2026-03-20T12:01:00Z",
  updated_at: "2026-03-20T12:06:00Z",
};

const policy = {
  project_id: "project-1",
  autonomy_mode: "recommend",
  require_human_approval: true,
  allow_production_writes: false,
  allow_low_risk_autonomy: true,
  block_during_active_deploys: true,
  restrict_to_approved_services: false,
  require_rollback_plan: true,
  require_post_action_verification: true,
  approved_services: ["billing-api"],
  failure_classifier_enabled: true,
  root_cause_enabled: true,
  patch_planner_enabled: true,
  runbook_executor_enabled: false,
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:00:00Z",
};

const user = {
  id: "user-1",
  email: "connor@example.com",
  full_name: "Connor GA",
  email_verified_at: "2026-03-20T12:00:00Z",
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:00:00Z",
};

const organization = {
  id: "org-1",
  name: "Stimpact",
  slug: "stimpact",
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:00:00Z",
};

const projectSummary = {
  id: "project-1",
  organization_id: "org-1",
  slug: "synthetic-soul-songs",
  name: "Synthetic Soul Songs",
  created_by_user_id: "user-1",
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:00:00Z",
};

const session = {
  access_token: await new SignJWT({
    org_id: "org-1",
    role: "owner",
    type: "session",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject("user-1")
    .setIssuedAt(Math.floor(Date.now() / 1000))
    .setExpirationTime("7d")
    .sign(new TextEncoder().encode("stimpact-dev-session-secret")),
  user,
  organization,
  role: "owner",
  memberships: [
    {
      organization,
      role: "owner",
    },
  ],
  projects: [projectSummary],
  subscription: {
    id: "subscription-1",
    organization_id: "org-1",
    plan: "scale",
    status: "active",
    included_projects: 3,
    additional_project_price_cents: 3000,
    seat_policy: "unlimited",
    created_at: "2026-03-20T12:00:00Z",
    updated_at: "2026-03-20T12:00:00Z",
  },
};

const baseSecretRef = {
  id: "secret-1",
  project_id: "project-1",
  label: "OPENAI_API_KEY",
  description: "Runtime secret",
  backend: "aws_secrets_manager",
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:00:00Z",
};

const baseProviderRepository = {
  id: "provider-repo-1",
  provider_integration_id: "integration-1",
  provider: "github",
  external_repository_id: "123",
  owner: "acme",
  name: "billing-api",
  default_branch: "main",
  clone_url: "https://github.com/acme/billing-api.git",
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:00:00Z",
};

const baseProviderIntegration = {
  id: "integration-1",
  provider: "github",
  name: "Acme GitHub",
  status: "active",
  credentials_secret_ref_id: "secret-1",
  webhook_secret_ref_id: null,
  aws_region: "us-west-2",
  metadata: {
    project_id: "project-1",
  },
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:00:00Z",
};

const baseRepoProfile = {
  id: "profile-1",
  project_id: "project-1",
  provider_repository_id: "provider-repo-1",
  runtime_kind: "python",
  base_image: "public.ecr.aws/docker/library/python:3.12",
  install_command: "pip install -r requirements.txt",
  startup_commands: ["python app.py"],
  reproduce_command: "python reproduce.py",
  verify_command: "pytest",
  success_criteria: "Tests pass after the patch is applied.",
  network_allowlist: ["pypi.org"],
  secret_refs: [],
  secret_mounts: [],
  active: true,
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:00:00Z",
};

const projectApiKey = {
  id: "api-key-1",
  project_id: "project-1",
  name: "SDK ingest",
  key_prefix: "stimp_live_demo",
  status: "active",
  last_used_at: "2026-03-20T12:03:00Z",
  revoked_at: null,
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:03:00Z",
};

const projectBrowserKey = {
  id: "browser-key-1",
  project_id: "project-1",
  name: "Browser telemetry",
  key_prefix: "stimp_browser_demo",
  allowed_origins: ["https://app.example.com"],
  status: "active",
  last_used_at: "2026-03-20T12:03:00Z",
  last_issued_at: "2026-03-20T12:03:00Z",
  revoked_at: null,
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-20T12:03:00Z",
};

const autonomousDetail = {
  run: autonomousRun,
  events: [],
  outcome: null,
  artifact_paths: {
    snapshot_path: ".stimpactai/autonomous-runs/run-1/snapshot.json",
    events_path: ".stimpactai/autonomous-runs/run-1/events.jsonl",
    outcome_path: null,
  },
};

let secretRefs = [structuredClone(baseSecretRef)];
let providerIntegrations = [structuredClone(baseProviderIntegration)];
let providerRepositoriesByIntegration = {
  "integration-1": [structuredClone(baseProviderRepository)],
};
let repoProfiles = [structuredClone(baseRepoProfile)];
const sdkBootstrapStrategy = {
  id: "nextjs-app-router",
  language: "typescript",
  framework: "Next.js App Router",
  summary: "Initialize the Stimpact SDK from the app router entrypoint and expose the required env vars.",
  confidence: "high",
  pr_supported: true,
  target_subpath: "apps/web",
  entrypoints: ["apps/web/src/app/layout.tsx"],
  assumptions: [],
  blockers: [],
  planned_files: [
    {
      path: "apps/web/src/app/layout.tsx",
      action: "update",
      reason: "Attach the SDK initialization to the app entrypoint.",
    },
    {
      path: "apps/web/.env.example",
      action: "update",
      reason: "Document the required Stimpact environment variables.",
    },
  ],
  env_vars: [
    {
      name: "NEXT_PUBLIC_STIMPACT_BASE_URL",
      example_value: "https://stimpact.example.com",
      description: "Public Stimpact platform URL.",
    },
    {
      name: "NEXT_PUBLIC_STIMPACT_PROJECT_ID",
      example_value: "project-1",
      description: "Project identifier used by the SDK.",
    },
    {
      name: "NEXT_PUBLIC_STIMPACT_BROWSER_KEY",
      example_value: "stimp_browser_replace_me",
      description: "Browser telemetry key used to request short-lived ingest tokens.",
    },
  ],
  install_command: "pnpm add @stimpact/sdk",
  package_name: "@stimpact/sdk",
  manual_steps: [
    {
      title: "Install the SDK",
      content: "Run `pnpm add @stimpact/sdk` from the app workspace.",
    },
    {
      title: "Initialize at startup",
      content:
        "Import and initialize the SDK from `src/app/layout.tsx`, then wire handled request and mutation failures with `captureHandledError()` or `wrapAsync()`.",
    },
  ],
  preview_snippet:
    "import { StimpactClient } from '@stimpact/sdk';\n\nconst stimpact = new StimpactClient({\n  baseUrl: '<public-stimpact-url>',\n  projectId: '<project-id>',\n  browserKey: '<browser-key>',\n  service: 'web-app',\n  environment: 'production',\n});\n\nstimpact.startHeartbeat();\nstimpact.registerBrowserAutoCapture();\n\nexport async function captureHandledError(input) {\n  await stimpact.captureHandledError(input);\n}\n\nexport async function pingStimpact() {\n  await stimpact.ping();\n}",
  source: "deterministic",
  evidence: ["Detected app router layout at apps/web/src/app/layout.tsx"],
  confidence_reason: "The repo contains a supported Next.js App Router entrypoint.",
};

function buildOnboardingResponse(projectId) {
  const integrations = providerIntegrations
    .filter((integration) => integration.metadata.project_id === projectId)
    .map((integration) => ({
      integration,
      repositories: providerRepositoriesByIntegration[integration.id] ?? [],
    }));

  const projectSecretRefs = secretRefs.filter((item) => item.project_id === projectId);
  const projectRepoProfiles = repoProfiles.filter((item) => item.project_id === projectId);
  const suggestedNextSteps = [];
  if (integrations.length === 0) {
    suggestedNextSteps.push("Connect GitHub or GitLab for this project.");
  }
  if (integrations.length > 0 && !integrations.some((item) => item.repositories.length > 0)) {
    suggestedNextSteps.push("Sync repositories from your connected provider account.");
  }
  if (projectSecretRefs.length === 0) {
    suggestedNextSteps.push("Add the runtime secrets your sandbox environment needs.");
  }
  if (projectRepoProfiles.length === 0) {
    suggestedNextSteps.push("Create a repo profile with reproduce and verify commands.");
  }
  if (suggestedNextSteps.length === 0) {
    suggestedNextSteps.push("Project onboarding looks complete. Run a sandbox verification to validate the setup.");
  }

  return {
    project_id: projectId,
    platform_base_url: "https://stimpact.example.com",
    policy,
    onboarding_state: {
      project_id: projectId,
      policy_reviewed: false,
      sdk_setup_status: "pending",
      sdk_setup_provider_repository_id: null,
      sdk_setup_change_request_url: null,
      created_at: "2026-03-20T12:00:00Z",
      updated_at: "2026-03-20T12:00:00Z",
    },
    operational_readiness: {
      has_provider_connection: integrations.length > 0,
      has_synced_repositories: integrations.some((item) => item.repositories.length > 0),
      has_secrets: projectSecretRefs.length > 0,
      has_repo_profiles: projectRepoProfiles.length > 0,
      has_services: false,
      has_active_api_keys: true,
      has_active_browser_keys: true,
      policy_reviewed: false,
      sdk_setup_ready: false,
      complete: false,
    },
    secret_refs: projectSecretRefs,
    api_keys: [projectApiKey],
    browser_keys: [projectBrowserKey],
    integrations,
    repo_profiles: projectRepoProfiles,
    project_services: [],
    telemetry_heartbeats: [],
    suggested_next_steps: suggestedNextSteps,
  };
}

function buildIncidentReportingOverview(projectId = null) {
  const incidents = [incident].filter((item) => !projectId || item.project_id === projectId);
  return {
    project_id: projectId,
    total_visible_incidents: incidents.length,
    open_incidents: incidents.filter((item) => item.status === "open").length,
    critical_incidents: incidents.filter((item) => item.severity === "critical").length,
    total_event_volume: incidents.reduce((sum, item) => sum + item.event_count, 0),
    latest_incident_at: incidents[0]?.last_seen_at ?? null,
    service_counts: [{ label: "billing-api", count: incidents.length }],
    environment_counts: [{ label: "production", count: incidents.length }],
    severity_counts: [
      { label: "critical", count: incidents.filter((item) => item.severity === "critical").length },
      { label: "high", count: incidents.filter((item) => item.severity === "high").length },
      { label: "medium", count: incidents.filter((item) => item.severity === "medium").length },
      { label: "low", count: incidents.filter((item) => item.severity === "low").length },
    ],
    recent_incident_activity: [
      { label: "00:00", count: 0 },
      { label: "04:00", count: 0 },
      { label: "08:00", count: 0 },
      { label: "12:00", count: incidents.length },
      { label: "16:00", count: 0 },
      { label: "20:00", count: 0 },
    ],
    daily_incident_activity: [
      { label: "Mon", count: 0 },
      { label: "Tue", count: 0 },
      { label: "Wed", count: 0 },
      { label: "Thu", count: 0 },
      { label: "Fri", count: 1 },
      { label: "Sat", count: 0 },
      { label: "Sun", count: 0 },
    ],
  };
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1:4010");

  if (url.pathname === "/incidents") {
    return json(response, {
      items: [incident],
      total: 1,
      limit: Number(url.searchParams.get("limit") ?? "1"),
      offset: Number(url.searchParams.get("offset") ?? "0"),
    });
  }

  if (url.pathname === "/incidents/reporting/overview") {
    return json(response, buildIncidentReportingOverview(url.searchParams.get("project_id")));
  }

  if (url.pathname === `/incidents/${incident.id}/autonomous-runs/latest`) {
    return json(response, autonomousDetail);
  }

  if (url.pathname === "/health/ready") {
    return json(response, {
      status: "ready",
      checks: {
        database: {
          configured: true,
          ready: true,
        },
      },
    });
  }

  if (url.pathname === "/auth/me") {
    return json(response, session);
  }

  if (url.pathname === "/auth/login" && request.method === "POST") {
    return json(response, session);
  }

  if (url.pathname === "/control-plane/provider-integrations") {
    return json(response, providerIntegrations);
  }

  if (url.pathname === `/control-plane/projects/project-1/policy`) {
    return json(response, policy);
  }

  if (url.pathname === `/control-plane/projects/project-1/api-keys`) {
    return json(response, [projectApiKey]);
  }

  if (url.pathname === "/control-plane/repo-profiles") {
    return json(response, repoProfiles);
  }

  if (url.pathname === "/control-plane/secret-refs") {
    return json(response, secretRefs);
  }

  if (url.pathname === "/control-plane/projects/project-1/bootstrap") {
    return json(response, buildOnboardingResponse("project-1"));
  }

  if (url.pathname === "/control-plane/projects/project-1/onboarding") {
    return json(response, buildOnboardingResponse("project-1"));
  }

  if (
    url.pathname ===
      "/control-plane/projects/project-1/provider-repositories/provider-repo-1/repo-profile-defaults" &&
    request.method === "GET"
  ) {
    return json(response, {
      runtime_kind: "node",
      base_image: "public.ecr.aws/docker/library/node:20",
      install_command: "pnpm install --frozen-lockfile",
      reproduce_command: "pnpm --dir apps/web run test",
      verify_command: "pnpm --dir apps/web run test",
      detected_from: ["package.json and lockfile", "package.json scripts in apps/web"],
      warnings: [
        "This repository looks like a monorepo. If frontend and backend deploy separately, map them as separate services.",
      ],
      monorepo: true,
    });
  }

  if (url.pathname === "/control-plane/projects/project-1/sdk-bootstrap/plan" && request.method === "POST") {
    return void readJson(request).then((payload) => {
      if (!payload.project_id || !payload.provider_repository_id || !payload.service_name || !payload.base_url) {
        return json(
          response,
          {
            detail: "Missing required SDK bootstrap plan fields.",
          },
          400,
        );
      }
      json(response, {
        runtime: "node",
        warnings: [],
        strategies: [
          {
            ...sdkBootstrapStrategy,
            env_vars: sdkBootstrapStrategy.env_vars.map((item) =>
              item.name === "NEXT_PUBLIC_STIMPACT_BASE_URL"
                    ? { ...item, example_value: payload.base_url }
                  : item.name === "NEXT_PUBLIC_STIMPACT_PROJECT_ID"
                      ? { ...item, example_value: payload.project_id }
                      : item,
            ),
          },
        ],
        recommended_strategy_id: sdkBootstrapStrategy.id,
        requires_confirmation: true,
      });
    });
  }

  if (url.pathname === "/control-plane/projects/project-1/sdk-bootstrap/preview" && request.method === "POST") {
    return void readJson(request).then((payload) => {
      if (
        !payload.project_id ||
        !payload.provider_repository_id ||
        !payload.service_name ||
        !payload.base_url
      ) {
        return json(
          response,
          {
            detail: "Missing required SDK bootstrap preview fields.",
          },
          400,
        );
      }
      const selectedStrategyId = payload.strategy_id ?? sdkBootstrapStrategy.id;
      const attempt = {
        strategy_id: selectedStrategyId,
        patch_source: "deterministic",
        patch_generated: true,
        patch_applied: true,
        verification: {
          status: "passed",
          command: "review-generated-patch",
          summary: "Patch applied in a temp checkout and passed focused verification.",
          output: null,
        },
        preview_available: true,
        change_request_allowed: true,
        changed_files: ["apps/web/src/app/layout.tsx", "apps/web/.env.example"],
        warnings: [],
        failure_stage: null,
        failure_reason: null,
        rejection_reason_code: null,
        attempt_number: 2,
        candidate_id: selectedStrategyId,
        generation_duration_ms: 320,
        apply_duration_ms: 90,
        verification_duration_ms: 120,
      };
      json(response, {
        run_id: "sdk-run-1",
        selected_strategy_id: selectedStrategyId,
        strategy: {
          ...sdkBootstrapStrategy,
          env_vars: sdkBootstrapStrategy.env_vars.map((item) =>
            item.name === "NEXT_PUBLIC_STIMPACT_BASE_URL"
                  ? { ...item, example_value: payload.base_url }
                  : item.name === "NEXT_PUBLIC_STIMPACT_PROJECT_ID"
                    ? { ...item, example_value: payload.project_id }
                    : item,
          ),
        },
        pull_request: {
          branch_name: "stimpact/sdk-bootstrap-preview",
          title: "Add Stimpact SDK bootstrap",
          description: "## Summary\n- initialize the Stimpact SDK in the app router entrypoint",
          commit_message: "Add Stimpact SDK bootstrap",
        },
        patch_diff:
          "diff --git a/apps/web/src/app/layout.tsx b/apps/web/src/app/layout.tsx\n+import { initStimpact } from '@stimpact/sdk';\n+initStimpact({ baseUrl: 'https://stimpact.example.com', projectId: 'project-1' });\n",
        attempt,
        attempts: [
          {
            strategy_id: "javascript-react-scripts:apps/web:src/index.tsx",
            patch_source: "llm",
            patch_generated: false,
            patch_applied: false,
            verification: {
              status: "skipped",
              command: null,
              summary: "First candidate did not produce a reviewable patch.",
              output: null,
            },
            preview_available: false,
            change_request_allowed: false,
            changed_files: [],
            warnings: ["First candidate was rejected before preview."],
            failure_stage: "generation",
            failure_reason: "First candidate did not produce a reviewable patch.",
            rejection_reason_code: "empty_patch",
            attempt_number: 1,
            candidate_id: "javascript-react-scripts:apps/web:src/index.tsx",
            generation_duration_ms: 120,
            apply_duration_ms: null,
            verification_duration_ms: null,
          },
          attempt,
        ],
      });
    });
  }

  if (
    url.pathname === "/control-plane/projects/project-1/telemetry-verification" &&
    request.method === "GET"
  ) {
    return json(response, {
      service: url.searchParams.get("service") ?? "web-app",
      environment: url.searchParams.get("environment") ?? "production",
      status: "unseen",
      last_seen_at: null,
      commit_sha: null,
      stale_after_seconds: 300,
      heartbeat: null,
    });
  }

  if (url.pathname === "/control-plane/projects/project-1/secret-refs" && request.method === "POST") {
    return void readJson(request).then((payload) => {
      const created = {
        id: `secret-${secretRefs.length + 1}`,
        project_id: payload.project_id,
        label: payload.label,
        description: payload.description ?? null,
        backend: "aws_secrets_manager",
        created_at: "2026-03-21T12:00:00Z",
        updated_at: "2026-03-21T12:00:00Z",
      };
      secretRefs = [...secretRefs, created];
      json(response, created, 201);
    });
  }

  if (
    url.pathname === "/control-plane/projects/project-1/provider-integrations/github-app/start" &&
    request.method === "POST"
  ) {
    return void readJson(request).then((payload) => {
      const created = {
        id: `integration-${providerIntegrations.length + 1}`,
        provider: "github",
        name: payload.name,
        status: "disabled",
        credentials_secret_ref_id: null,
        webhook_secret_ref_id: null,
        aws_region: "us-west-2",
        metadata: {
          project_id: payload.project_id,
          redirect_url: payload.redirect_url,
        },
        created_at: "2026-03-21T12:00:00Z",
        updated_at: "2026-03-21T12:00:00Z",
      };
      providerIntegrations = [...providerIntegrations, created];
      providerRepositoriesByIntegration = {
        ...providerRepositoriesByIntegration,
        [created.id]: [],
      };
      json(
        response,
        {
          integration: created,
          installation_url: "https://github.com/apps/stimpact/installations/new?state=github-install-state",
        },
        201,
      );
    });
  }

  if (url.pathname === "/control-plane/projects/project-1/provider-integrations/github-app" && request.method === "POST") {
    return void readJson(request).then((payload) => {
      const created = {
        id: `integration-${providerIntegrations.length + 1}`,
        provider: "github",
        name: payload.name,
        status: "active",
        credentials_secret_ref_id: null,
        webhook_secret_ref_id: null,
        aws_region: "us-west-2",
        metadata: {
          project_id: payload.project_id,
          installation_id: payload.installation_id ?? "117170229",
        },
        created_at: "2026-03-21T12:00:00Z",
        updated_at: "2026-03-21T12:00:00Z",
      };
      providerIntegrations = [...providerIntegrations, created];
      providerRepositoriesByIntegration = {
        ...providerRepositoriesByIntegration,
        [created.id]: [],
      };
      json(response, created, 201);
    });
  }

  if (url.pathname === "/control-plane/projects/project-1/provider-integrations/gitlab/oauth/start" && request.method === "POST") {
    return void readJson(request).then((payload) => {
      const created = {
        id: `integration-${providerIntegrations.length + 1}`,
        provider: "gitlab",
        name: payload.name,
        status: "disabled",
        credentials_secret_ref_id: null,
        webhook_secret_ref_id: null,
        aws_region: "us-west-2",
        metadata: {
          project_id: payload.project_id,
          gitlab_base_url: payload.gitlab_base_url ?? "https://gitlab.com",
        },
        created_at: "2026-03-21T12:00:00Z",
        updated_at: "2026-03-21T12:00:00Z",
      };
      providerIntegrations = [...providerIntegrations, created];
      providerRepositoriesByIntegration = {
        ...providerRepositoriesByIntegration,
        [created.id]: [],
      };
      json(
        response,
        {
          integration: created,
          authorization_url: "https://gitlab.com/oauth/authorize?client_id=abc",
        },
        201,
      );
    });
  }

  if (
    url.pathname === "/control-plane/projects/project-1/provider-integrations/integration-1/repositories/sync" &&
    request.method === "POST"
  ) {
    providerRepositoriesByIntegration = {
      ...providerRepositoriesByIntegration,
      "integration-1": [structuredClone(baseProviderRepository)],
    };
    return json(response, {
      integration: providerIntegrations.find((item) => item.id === "integration-1"),
      repositories: providerRepositoriesByIntegration["integration-1"],
    });
  }

  if (
    url.pathname === "/control-plane/projects/project-1/provider-integrations/integration-1/repositories"
  ) {
    return json(response, providerRepositoriesByIntegration["integration-1"] ?? []);
  }

  if (url.pathname === "/control-plane/projects/project-1/repo-profiles" && request.method === "POST") {
    return void readJson(request).then((payload) => {
      const attachedSecret = secretRefs.find((item) => item.id === payload.secret_mounts?.[0]?.secret_ref_id);
      const created = {
        id: `profile-${repoProfiles.length + 1}`,
        project_id: payload.project_id,
        provider_repository_id: payload.provider_repository_id,
        runtime_kind: payload.runtime_kind,
        base_image: payload.base_image ?? null,
        install_command: payload.install_command ?? null,
        startup_commands: payload.startup_commands ?? [],
        reproduce_command: payload.reproduce_command,
        verify_command: payload.verify_command,
        success_criteria: payload.success_criteria ?? null,
        network_allowlist: payload.network_allowlist ?? [],
        secret_refs: attachedSecret ? [attachedSecret] : [],
        secret_mounts: attachedSecret
          ? [
              {
                mount_as: payload.secret_mounts[0].mount_as,
                secret_ref: attachedSecret,
              },
            ]
          : [],
        active: true,
        created_at: "2026-03-21T12:00:00Z",
        updated_at: "2026-03-21T12:00:00Z",
      };
      repoProfiles = [...repoProfiles, created];
      json(response, created, 201);
    });
  }

  response.statusCode = 404;
  response.end("Not found");
});

server.listen(4010, "127.0.0.1");

function json(response, payload, statusCode = 200) {
  response.statusCode = statusCode;
  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify(payload));
}
