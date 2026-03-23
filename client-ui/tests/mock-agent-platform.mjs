import http from "node:http";

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

const baseSecretRef = {
  id: "secret-1",
  project_id: "project-1",
  label: "OPENAI_API_KEY",
  description: "Runtime secret",
  backend: "aws_secrets_manager",
  external_ref: "arn:aws:secretsmanager:us-west-2:123456789012:secret:project-1/openai",
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
    policy,
    secret_refs: projectSecretRefs,
    api_keys: [projectApiKey],
    integrations,
    repo_profiles: projectRepoProfiles,
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

  if (url.pathname === "/control-plane/projects/project-1/secret-refs" && request.method === "POST") {
    return void readJson(request).then((payload) => {
      const created = {
        id: `secret-${secretRefs.length + 1}`,
        project_id: payload.project_id,
        label: payload.label,
        description: payload.description ?? null,
        backend: "aws_secrets_manager",
        external_ref: `arn:aws:secretsmanager:us-west-2:123456789012:secret:${payload.project_id}/${payload.label}`,
        created_at: "2026-03-21T12:00:00Z",
        updated_at: "2026-03-21T12:00:00Z",
      };
      secretRefs = [...secretRefs, created];
      json(response, created, 201);
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
