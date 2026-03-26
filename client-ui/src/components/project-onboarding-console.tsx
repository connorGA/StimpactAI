"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  AuthSession,
  GitLabOAuthStartResponse,
  ProjectOnboarding,
  ProjectSummary,
  ProviderRepository,
} from "@/lib/types";

type ApiErrorPayload = {
  error?: {
    message?: string;
  };
};

const STEP_ORDER = ["1", "2", "3", "4", "5"] as const;

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/onboarding/${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let message = `Onboarding request failed with status ${response.status}.`;
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (payload.error?.message) {
        message = payload.error.message;
      }
    } catch {
      // Keep the default fallback when the payload is not JSON.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export function ProjectOnboardingConsole() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [projectId, setProjectId] = useState("");
  const [state, setState] = useState<ProjectOnboarding | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("Production");
  const [newProjectSlug, setNewProjectSlug] = useState("production");

  const [githubName, setGithubName] = useState("Acme GitHub");
  const [githubInstallationId, setGithubInstallationId] = useState("");
  const [gitlabName, setGitlabName] = useState("Acme GitLab");
  const [gitlabBaseUrl, setGitlabBaseUrl] = useState("");
  const [lastGitLabAuthUrl, setLastGitLabAuthUrl] = useState<string | null>(null);

  const [secretLabel, setSecretLabel] = useState("OPENAI_API_KEY");
  const [secretDescription, setSecretDescription] = useState("Runtime secret");
  const [secretValue, setSecretValue] = useState("");

  const [runtimeKind, setRuntimeKind] = useState<"python" | "node" | "generic" | "container">("python");
  const [baseImage, setBaseImage] = useState("public.ecr.aws/docker/library/python:3.12");
  const [installCommand, setInstallCommand] = useState("pip install -r requirements.txt");
  const [reproduceCommand, setReproduceCommand] = useState("pytest");
  const [verifyCommand, setVerifyCommand] = useState("pytest");
  const [networkAllowlist, setNetworkAllowlist] = useState("pypi.org");
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [selectedSecretRefId, setSelectedSecretRefId] = useState("");
  const [secretMountAs, setSecretMountAs] = useState("OPENAI_API_KEY");
  const [activeStep, setActiveStep] = useState<(typeof STEP_ORDER)[number]>("1");
  const stepRefs = useRef<Record<string, HTMLElement | null>>({});

  const repositories = useMemo<ProviderRepository[]>(() => {
    if (!state) {
      return [];
    }
    return state.integrations.flatMap((integration) => integration.repositories);
  }, [state]);

  const loadOnboardingState = useCallback(async (bootstrap = false) => {
    const encodedProjectId = encodeURIComponent(projectId.trim());
    const payload = await requestJson<ProjectOnboarding>(
      `projects/${encodedProjectId}/${bootstrap ? "bootstrap" : "onboarding"}`,
      {
        method: bootstrap ? "POST" : "GET",
      },
    );
    setState(payload);
    if (!selectedRepositoryId && payload.integrations[0]?.repositories[0]?.id) {
      setSelectedRepositoryId(payload.integrations[0].repositories[0].id);
    }
    if (!selectedSecretRefId && payload.secret_refs[0]?.id) {
      setSelectedSecretRefId(payload.secret_refs[0].id);
      setSecretMountAs(payload.secret_refs[0].label);
    }
  }, [projectId, selectedRepositoryId, selectedSecretRefId]);

  useEffect(() => {
    async function loadSession() {
      try {
        const response = await fetch("/api/auth/session", {
          method: "GET",
        });
        if (!response.ok) {
          throw new Error("Unable to load session.");
        }
        const payload = (await response.json()) as Omit<AuthSession, "access_token">;
        const normalized = { ...payload, access_token: "" } as AuthSession;
        setSession(normalized);
        if (payload.projects[0]?.id) {
          setProjectId(payload.projects[0].id);
        }
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "Unable to load session.");
      }
    }
    void loadSession();
  }, []);

  useEffect(() => {
    if (!projectId.trim()) {
      return;
    }
    void loadOnboardingState(false).catch((error) => {
      setErrorMessage(error instanceof Error ? error.message : "Unable to load onboarding.");
    });
  }, [loadOnboardingState, projectId]);

  useEffect(() => {
    function updateActiveStep() {
      const closestStep = STEP_ORDER
        .map((step) => {
          const node = stepRefs.current[step];
          if (!node) {
            return { step, distance: Number.POSITIVE_INFINITY };
          }
          const top = node.getBoundingClientRect().top;
          return { step, distance: Math.abs(top - 140) };
        })
        .sort((left, right) => left.distance - right.distance)[0];

      if (closestStep && Number.isFinite(closestStep.distance)) {
        setActiveStep(closestStep.step);
      }
    }

    updateActiveStep();
    window.addEventListener("scroll", updateActiveStep, { passive: true });
    window.addEventListener("resize", updateActiveStep);
    return () => {
      window.removeEventListener("scroll", updateActiveStep);
      window.removeEventListener("resize", updateActiveStep);
    };
  }, []);

  async function withFeedback(
    action: () => Promise<void>,
    successMessage: string,
  ) {
    setLoading(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      await action();
      setStatusMessage(successMessage);
    } catch (caughtError) {
      setErrorMessage(
        caughtError instanceof Error
          ? caughtError.message
          : "Unexpected onboarding error.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function bootstrapProject() {
    await withFeedback(async () => {
      await loadOnboardingState(true);
    }, "Project onboarding state loaded.");
  }

  async function refreshProject() {
    await withFeedback(async () => {
      await loadOnboardingState(false);
    }, "Project onboarding state refreshed.");
  }

  async function connectGitHub() {
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/provider-integrations/github-app`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            name: githubName,
            installation_id: githubInstallationId || undefined,
          }),
        },
      );
      await loadOnboardingState(false);
    }, "GitHub integration connected.");
  }

  async function startGitLab() {
    await withFeedback(async () => {
      const response = await requestJson<GitLabOAuthStartResponse>(
        `projects/${encodeURIComponent(projectId.trim())}/provider-integrations/gitlab/oauth/start`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            name: gitlabName,
            gitlab_base_url: gitlabBaseUrl || undefined,
          }),
        },
      );
      setLastGitLabAuthUrl(response.authorization_url);
      await loadOnboardingState(false);
    }, "GitLab OAuth session created.");
  }

  async function syncRepositories(providerIntegrationId: string) {
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/provider-integrations/${encodeURIComponent(providerIntegrationId)}/repositories/sync`,
        {
          method: "POST",
        },
      );
      await loadOnboardingState(false);
    }, "Provider repositories synced.");
  }

  async function addSecret() {
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/secret-refs`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            label: secretLabel,
            description: secretDescription || null,
            value: secretValue,
          }),
        },
      );
      setSecretValue("");
      await loadOnboardingState(false);
    }, "Secret stored in AWS Secrets Manager.");
  }

  async function createRepoProfile() {
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/repo-profiles`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            provider_repository_id: selectedRepositoryId,
            runtime_kind: runtimeKind,
            base_image: baseImage || null,
            install_command: installCommand || null,
            startup_commands: [],
            reproduce_command: reproduceCommand,
            verify_command: verifyCommand,
            success_criteria: "Sandbox verification exits successfully after the generated patch is applied.",
            network_allowlist: networkAllowlist
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            secret_mounts:
              selectedSecretRefId && secretMountAs
                ? [
                    {
                      secret_ref_id: selectedSecretRefId,
                      mount_as: secretMountAs,
                    },
                  ]
                : [],
          }),
        },
      );
      await loadOnboardingState(false);
    }, "Repo profile created.");
  }

  async function createFirstProject() {
    setCreatingProject(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const response = await fetch("/api/auth/projects", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: newProjectName,
          slug: newProjectSlug,
        }),
      });
      const payload = (await response.json()) as
        | ProjectSummary
        | { error?: { message?: string } };
      if (!response.ok || !("id" in payload)) {
        throw new Error(
          "error" in payload ? payload.error?.message ?? "Project creation failed." : "Project creation failed.",
        );
      }
      const sessionResponse = await fetch("/api/auth/session", { method: "GET" });
      if (sessionResponse.ok) {
        const sessionPayload = (await sessionResponse.json()) as Omit<AuthSession, "access_token">;
        setSession({ ...sessionPayload, access_token: "" } as AuthSession);
      }
      setProjectId(payload.id);
      setStatusMessage("Project created. Continue with provider, secret, and repo profile setup.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Project creation failed.");
    } finally {
      setCreatingProject(false);
    }
  }

  const hasProject = projectId.trim().length > 0;
  const hasIntegrations = (state?.integrations.length ?? 0) > 0;
  const hasRepositories = repositories.length > 0;
  const hasSecrets = (state?.secret_refs.length ?? 0) > 0;
  const hasRepoProfiles = (state?.repo_profiles.length ?? 0) > 0;

  return (
    <div className="space-y-5">
      <section className="relative px-4 pb-2 pt-2 text-center">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_26%_12%,rgba(255,178,83,0.12),transparent_24%),radial-gradient(circle_at_74%_14%,rgba(255,106,61,0.12),transparent_22%),radial-gradient(circle_at_50%_0%,rgba(29,26,24,0.06),transparent_30%)] [mask-image:linear-gradient(180deg,rgba(0,0,0,0.58)_0%,rgba(0,0,0,0.24)_42%,transparent_78%)]" />
        <div className="relative mx-auto max-w-4xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#9b4c2f]">
            Project onboarding
          </p>
          <h1 className="mx-auto mt-4 max-w-4xl text-4xl font-semibold tracking-tight text-[#171717] lg:text-[3.35rem]">
            Set up your project in one guided flow
          </h1>
          <p className="mx-auto mt-5 max-w-3xl text-[15px] font-medium leading-8 text-[#64584f]">
            Move straight down the page to create the project, connect the repository
            provider, add secrets, and finish the repo profile that powers sandbox
            verification.
          </p>

          <OnboardingTimeline
            activeStep={activeStep}
            steps={[
              {
                step: "1",
                label: "Project",
                detail: "Create the project",
                complete: hasProject,
              },
              {
                step: "2",
                label: "Provider",
                detail: "Connect GitHub or GitLab",
                complete: hasIntegrations,
              },
              {
                step: "3",
                label: "Repository",
                detail: "Sync and choose the repo",
                complete: hasRepositories && Boolean(selectedRepositoryId),
              },
              {
                step: "4",
                label: "Secrets",
                detail: "Store runtime secrets",
                complete: hasSecrets,
              },
              {
                step: "5",
                label: "Profile",
                detail: "Finish the repo profile",
                complete: hasRepoProfiles,
              },
            ]}
          />

          {statusMessage ? <Banner tone="success" message={statusMessage} /> : null}
          {errorMessage ? <Banner tone="error" message={errorMessage} /> : null}
        </div>
      </section>

      <div className="space-y-4">
        <StepPanel
          step="01"
          stepKey="1"
          title="Create the first project"
          description={`Start here for ${session?.organization.name ?? "your workspace"}. Everything else below becomes active after the first project exists.`}
          complete={hasProject}
          sectionRef={(node) => {
            stepRefs.current["1"] = node;
          }}
        >
          {hasProject ? (
            <>
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
                <ReadOnlyField label="Workspace" value={session?.organization.name ?? "Workspace"} />
                <ReadOnlyField label="Project" value={projectId} />
                <ActionButton
                  label="Bootstrap"
                  onClick={bootstrapProject}
                  disabled={loading || !hasProject}
                />
                <ActionButton
                  label="Refresh"
                  onClick={refreshProject}
                  disabled={loading || !hasProject}
                  variant="secondary"
                />
              </div>
              <p className="mt-4 text-sm leading-6 text-[#5f6470]">
                Your onboarding actions are scoped to the authenticated workspace and
                selected project.
              </p>
            </>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Project name" value={newProjectName} onChange={setNewProjectName} />
                <Field label="Project slug" value={newProjectSlug} onChange={setNewProjectSlug} />
              </div>
              <ActionButton
                label={creatingProject ? "Creating project..." : "Create first project"}
                onClick={createFirstProject}
                disabled={creatingProject || !newProjectName.trim() || !newProjectSlug.trim()}
              />
            </div>
          )}
        </StepPanel>

        <StepPanel
          step="02"
          stepKey="2"
          title="Connect a git provider"
          description="Connect GitHub or GitLab first, then sync repositories from the integration you want this project to use."
          complete={hasIntegrations}
          sectionRef={(node) => {
            stepRefs.current["2"] = node;
          }}
        >
          <div className="grid gap-4 xl:grid-cols-2">
            <SubStepCard title="GitHub App">
              <Field label="Integration name" value={githubName} onChange={setGithubName} />
              <Field
                label="Installation ID"
                value={githubInstallationId}
                onChange={setGithubInstallationId}
                placeholder="Optional override"
              />
              <ActionButton
                label="Connect GitHub"
                onClick={connectGitHub}
                disabled={loading || !hasProject}
              />
            </SubStepCard>

            <SubStepCard title="GitLab OAuth" tone="warm">
              <Field label="Integration name" value={gitlabName} onChange={setGitlabName} />
              <Field
                label="GitLab base URL"
                value={gitlabBaseUrl}
                onChange={setGitlabBaseUrl}
                placeholder="https://gitlab.com"
              />
              <div className="flex flex-wrap items-center gap-3">
                <ActionButton
                  label="Start GitLab OAuth"
                  onClick={startGitLab}
                  disabled={loading || !hasProject}
                />
                {lastGitLabAuthUrl ? (
                  <a
                    href={lastGitLabAuthUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex text-sm font-medium text-[#3451d1] hover:underline"
                  >
                    Open GitLab authorization
                  </a>
                ) : null}
              </div>
            </SubStepCard>
          </div>
        </StepPanel>

        <StepPanel
          step="03"
          stepKey="3"
          title="Sync and choose repository"
          description="Once a provider is connected, sync repositories and select the repo that should power sandbox runs."
          complete={hasRepositories && Boolean(selectedRepositoryId)}
          sectionRef={(node) => {
            stepRefs.current["3"] = node;
          }}
        >
          <div className="space-y-4">
            {state?.integrations.length ? (
              state.integrations.map((integration) => (
                <div
                  key={integration.integration.id}
                  className="rounded-[22px] border border-[rgba(17,24,39,0.08)] bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(248,250,255,0.98))] p-5"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="font-semibold text-[#171717]">{integration.integration.name}</p>
                      <p className="mt-1 text-sm text-[#746d66]">
                        {integration.integration.provider} · {integration.repositories.length} synced repos
                      </p>
                    </div>
                    <ActionButton
                      label="Sync repos"
                      onClick={() => syncRepositories(integration.integration.id)}
                      disabled={loading}
                      variant="secondary"
                    />
                  </div>
                  {integration.repositories.length ? (
                    <ul className="mt-4 grid gap-2 text-sm text-[#35547d]">
                      {integration.repositories.map((repository) => (
                        <li key={repository.id}>
                          <label className="flex items-center gap-3 rounded-[16px] border border-[rgba(17,24,39,0.06)] bg-white px-4 py-3">
                            <input
                              type="radio"
                              name="provider_repository_id"
                              checked={selectedRepositoryId === repository.id}
                              onChange={() => setSelectedRepositoryId(repository.id)}
                            />
                            <span>
                              {repository.owner}/{repository.name} · default {repository.default_branch}
                            </span>
                          </label>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-4 text-sm text-[#746d66]">No repositories synced yet.</p>
                  )}
                </div>
              ))
            ) : (
              <p className="text-sm text-[#746d66]">
                Connect a provider first, then sync repositories here.
              </p>
            )}
          </div>
        </StepPanel>

        <StepPanel
          step="04"
          stepKey="4"
          title="Add runtime secrets"
          description="Store runtime secrets in AWS Secrets Manager and keep only metadata in the platform database."
          complete={hasSecrets}
          sectionRef={(node) => {
            stepRefs.current["4"] = node;
          }}
        >
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Secret label" value={secretLabel} onChange={setSecretLabel} />
              <Field label="Description" value={secretDescription} onChange={setSecretDescription} />
            </div>
            <Field
              label="Secret value"
              value={secretValue}
              onChange={setSecretValue}
              type="password"
              placeholder="Paste the secret value"
            />
            <ActionButton
              label="Store secret"
              onClick={addSecret}
              disabled={loading || !secretValue.trim()}
            />
            {state?.secret_refs.length ? (
              <ul className="grid gap-2 text-sm text-[#35547d]">
                {state.secret_refs.map((secretRef) => (
                  <li
                    key={secretRef.id}
                    className="rounded-[16px] border border-[rgba(17,24,39,0.06)] bg-white px-4 py-3"
                  >
                    {secretRef.label} · stored in {secretRef.backend}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-[#746d66]">No project secrets have been added yet.</p>
            )}
          </div>
        </StepPanel>

        <StepPanel
          step="05"
          stepKey="5"
          title="Create repo profile"
          description="Define how the sandbox installs dependencies, reproduces the issue, verifies the fix, and mounts secrets."
          complete={hasRepoProfiles}
          sectionRef={(node) => {
            stepRefs.current["5"] = node;
          }}
        >
          <div className="grid gap-4 md:grid-cols-2">
            <SelectField
              label="Runtime kind"
              value={runtimeKind}
              onChange={(value) =>
                setRuntimeKind(
                  value as "python" | "node" | "generic" | "container",
                )
              }
              options={[
                { value: "python", label: "Python" },
                { value: "node", label: "Node" },
                { value: "generic", label: "Generic" },
                { value: "container", label: "Container" },
              ]}
            />
            <Field label="Base image" value={baseImage} onChange={setBaseImage} />
            <Field label="Install command" value={installCommand} onChange={setInstallCommand} className="md:col-span-2" />
            <Field label="Reproduce command" value={reproduceCommand} onChange={setReproduceCommand} className="md:col-span-2" />
            <Field label="Verify command" value={verifyCommand} onChange={setVerifyCommand} className="md:col-span-2" />
            <Field
              label="Network allowlist"
              value={networkAllowlist}
              onChange={setNetworkAllowlist}
              placeholder="pypi.org, files.pythonhosted.org"
              className="md:col-span-2"
            />
            <SelectField
              label="Secret ref"
              value={selectedSecretRefId}
              onChange={setSelectedSecretRefId}
              options={[
                { value: "", label: "No secret mount" },
                ...(state?.secret_refs.map((secretRef) => ({
                  value: secretRef.id,
                  label: secretRef.label,
                })) ?? []),
              ]}
            />
            <Field
              label="Mount as"
              value={secretMountAs}
              onChange={setSecretMountAs}
              placeholder="OPENAI_API_KEY or /var/run/..."
            />
          </div>
          <div className="mt-4">
            <ActionButton
              label="Create repo profile"
              onClick={createRepoProfile}
              disabled={loading || !selectedRepositoryId || !reproduceCommand.trim() || !verifyCommand.trim()}
            />
          </div>
          {state?.repo_profiles.length ? (
            <ul className="mt-4 grid gap-2 text-sm text-[#35547d]">
              {state.repo_profiles.map((profile) => (
                <li
                  key={profile.id}
                  className="rounded-[16px] border border-[rgba(17,24,39,0.06)] bg-white px-4 py-3"
                >
                  {profile.runtime_kind} · verify <code>{profile.verify_command}</code>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-[#746d66]">No repo profile has been created yet.</p>
          )}
        </StepPanel>

        <section className="rounded-[28px] border border-[rgba(29,26,24,0.08)] bg-[linear-gradient(180deg,rgba(242,236,228,0.98),rgba(235,229,221,0.98))] p-6 shadow-[0_12px_32px_rgba(15,23,42,0.05)]">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8a8178]">
                Current onboarding state
              </p>
              {state ? (
                <ul className="mt-4 space-y-2 text-sm leading-6 text-[#5f6470]">
                  {state.suggested_next_steps.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-[#746d66]">
                  Bootstrap a project to begin the secure onboarding flow.
                </p>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
              <MiniStat label="Integrations" value={String(state?.integrations.length ?? 0)} />
              <MiniStat label="Repositories" value={String(repositories.length)} />
              <MiniStat label="Secrets" value={String(state?.secret_refs.length ?? 0)} />
              <MiniStat label="Repo profiles" value={String(state?.repo_profiles.length ?? 0)} />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function StepPanel({
  step,
  stepKey,
  title,
  description,
  complete,
  sectionRef,
  children,
}: {
  step: string;
  stepKey: string;
  title: string;
  description: string;
  complete?: boolean;
  sectionRef?: (node: HTMLElement | null) => void;
  children: ReactNode;
}) {
  return (
    <section
      id={`onboarding-step-${stepKey}`}
      ref={sectionRef}
      className="relative overflow-hidden rounded-[28px] border border-[rgba(29,26,24,0.1)] bg-[linear-gradient(180deg,rgba(255,251,247,0.98),rgba(249,242,234,0.98))] px-6 py-6 shadow-[0_18px_40px_rgba(15,23,42,0.06)]"
    >
      <div className="absolute left-0 top-0 h-full w-1.5 bg-[linear-gradient(180deg,#ffb253_0%,#ff6a3d_42%,#ff5a2a_100%)] opacity-95" />
      <div className="pl-3">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <span className="inline-flex rounded-full bg-[rgba(29,26,24,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#7c756d]">
                Step {step}
              </span>
              <StepStatus complete={complete} />
            </div>
            <h2 className="mt-3 text-2xl font-semibold text-[#171717]">{title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#5f6470]">{description}</p>
          </div>
        </div>
        <div className="mt-6">{children}</div>
      </div>
    </section>
  );
}

function SubStepCard({
  title,
  tone = "cool",
  children,
}: {
  title: string;
  tone?: "cool" | "warm";
  children: ReactNode;
}) {
  return (
    <div
      className={`space-y-4 rounded-[22px] border p-5 ${
        tone === "warm"
          ? "border-[rgba(255,178,83,0.14)] bg-[linear-gradient(180deg,rgba(245,236,227,0.98),rgba(239,229,220,0.98))]"
          : "border-[rgba(29,26,24,0.08)] bg-[linear-gradient(180deg,rgba(244,239,232,0.98),rgba(238,232,225,0.98))]"
      }`}
    >
      <p className="text-sm font-semibold text-[#171717]">{title}</p>
      {children}
    </div>
  );
}

function OnboardingTimeline({
  steps,
  activeStep,
}: {
  steps: Array<{
    step: (typeof STEP_ORDER)[number];
    label: string;
    detail: string;
    complete: boolean;
  }>;
  activeStep: (typeof STEP_ORDER)[number];
}) {
  return (
    <div className="mx-auto mt-8 max-w-[980px]">
      <div className="relative hidden overflow-visible pb-2 pt-2 lg:block">
        <div
          className="absolute left-[10%] right-[10%] top-[3.75rem] h-[2px] bg-[linear-gradient(90deg,rgba(255,190,153,0.32),rgba(255,106,61,0.68),rgba(255,190,153,0.32))]"
        />
        <div className="grid grid-cols-5 gap-2">
          {steps.map((item) => (
            <TimelineNode
              key={item.step}
              step={item.step}
              label={item.label}
              detail={item.detail}
              active={activeStep === item.step}
            />
          ))}
        </div>
      </div>

      <div className="grid gap-3 lg:hidden">
        {steps.map((item) => (
          <div
            key={item.step}
            className="flex items-start gap-3 rounded-[18px] border border-[rgba(29,26,24,0.08)] bg-[linear-gradient(180deg,rgba(255,250,246,0.96),rgba(245,239,232,0.98))] px-4 py-3 text-left shadow-[0_8px_24px_rgba(15,23,42,0.04)]"
          >
            <TimelineDot
              active={activeStep === item.step}
              step={item.step}
            />
            <div>
              <p className="text-sm font-semibold text-[#171717]">
                {item.step}. {item.label}
              </p>
              <p className="mt-1 text-xs leading-5 text-[#746d66]">{item.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TimelineNode({
  step,
  label,
  detail,
  active,
}: {
  step: string;
  label: string;
  detail: string;
  active: boolean;
}) {
  return (
    <div className="group relative px-1 pt-0 text-center">
      <div className="mx-auto flex w-full flex-col items-center">
        <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8a8178]">
          Step {step}
        </span>
        <div className="relative z-10 mt-2 flex h-14 items-center justify-center overflow-visible">
          <TimelineDot active={active} step={step} />
        </div>
        <div className="flex min-h-[86px] w-full flex-col items-center">
          <p className={`mt-1 text-sm font-semibold ${active ? "text-[#171717]" : "text-[#2f241f]"}`}>
            {label}
          </p>
          <p className="mt-1 max-w-[144px] text-[12px] font-medium leading-5 text-[#93867d]">
            {detail}
          </p>
        </div>
      </div>
    </div>
  );
}

function TimelineDot({
  active,
  step,
}: {
  active: boolean;
  step: string;
}) {
  return (
    <span
      className={`relative inline-flex h-11 w-11 items-center justify-center rounded-full border border-[rgba(255,106,61,0.24)] bg-[linear-gradient(180deg,#ff9d70_0%,#ff7d4d_56%,#ff6a3d_100%)] text-[11px] font-semibold transition duration-200 ease-out group-hover:-translate-y-0.5 group-hover:scale-[1.05] group-hover:shadow-[0_14px_28px_rgba(255,106,61,0.18)] ${
        active
          ? "text-white shadow-[0_0_0_7px_rgba(255,106,61,0.12),0_14px_28px_rgba(255,106,61,0.22)]"
          : "text-white/92"
      }`}
    >
      {step}
    </span>
  );
}

function StepStatus({ complete }: { complete?: boolean }) {
  return (
    <span
      className={`inline-flex rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${
        complete
          ? "bg-[rgba(22,164,109,0.12)] text-[#116346]"
          : "bg-[rgba(255,106,61,0.12)] text-[#9b4c2f]"
      }`}
    >
      {complete ? "Complete" : "In progress"}
    </span>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  className?: string;
}) {
  return (
    <label className={`block ${className ?? ""}`}>
      <span className="mb-2 block text-sm font-medium text-[#171717]">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-[16px] border border-[rgba(29,26,24,0.10)] bg-[rgba(255,250,245,0.82)] px-4 py-3 text-sm text-[#171717] outline-none transition placeholder:text-[#9c9388] focus:border-[rgba(255,106,61,0.36)] focus:bg-white"
      />
    </label>
  );
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="block">
      <span className="mb-2 block text-sm font-medium text-[#171717]">{label}</span>
      <div className="w-full rounded-[16px] border border-[rgba(29,26,24,0.10)] bg-[linear-gradient(180deg,#f2eae1,#ede4da)] px-4 py-3 text-sm text-[#171717]">
        {value}
      </div>
    </div>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-[#171717]">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-[16px] border border-[rgba(29,26,24,0.10)] bg-[rgba(255,250,245,0.82)] px-4 py-3 text-sm text-[#171717] outline-none transition focus:border-[rgba(255,106,61,0.36)] focus:bg-white"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ActionButton({
  label,
  onClick,
  disabled,
  variant = "primary",
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center rounded-[16px] px-4 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${
        variant === "secondary"
          ? "border border-[rgba(29,26,24,0.08)] bg-[rgba(255,250,245,0.84)] text-[#17385d] hover:border-[rgba(255,106,61,0.2)] hover:bg-[#fff5ef]"
          : "bg-[linear-gradient(180deg,#ff754b_0%,#ff5a2a_100%)] text-white shadow-[0_14px_28px_rgba(255,106,61,0.2)] hover:-translate-y-0.5 hover:shadow-[0_18px_34px_rgba(255,106,61,0.26)]"
      }`}
    >
      {label}
    </button>
  );
}

function Banner({
  tone,
  message,
}: {
  tone: "success" | "error";
  message: string;
}) {
  return (
    <div
      className={`mt-4 rounded-[16px] px-4 py-3 text-sm ${
        tone === "success"
          ? "bg-[rgba(67,160,71,0.12)] text-[#2f6f35]"
          : "bg-[rgba(198,40,40,0.10)] text-[#8c2d2d]"
      }`}
    >
      {message}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-[rgba(29,26,24,0.06)] bg-[linear-gradient(180deg,#f6efe7,#f0e8de)] px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-[#171717]">{value}</p>
    </div>
  );
}
