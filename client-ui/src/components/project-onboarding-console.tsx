"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

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

  return (
    <div className="space-y-6">
      <section className="vault-panel-strong rounded-[24px] p-6">
        {projectId.trim() ? (
          <>
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto_auto]">
              <ReadOnlyField
                label="Workspace"
                value={session?.organization.name ?? "Workspace"}
              />
              <ReadOnlyField label="Project" value={projectId} />
              <ActionButton label="Bootstrap" onClick={bootstrapProject} disabled={loading || !projectId.trim()} />
              <ActionButton label="Refresh" onClick={refreshProject} disabled={loading || !projectId.trim()} />
            </div>
            <p className="mt-3 text-sm leading-6 text-[#746d66]">
              Your onboarding actions are now scoped to the authenticated workspace and selected project.
            </p>
          </>
        ) : (
          <div className="space-y-4">
            <p className="text-sm leading-6 text-[#746d66]">
              Create the first protected project for {session?.organization.name ?? "your workspace"} before
              connecting repositories or storing runtime secrets.
            </p>
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
        {statusMessage ? <Banner tone="success" message={statusMessage} /> : null}
        {errorMessage ? <Banner tone="error" message={errorMessage} /> : null}
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Panel
          title="1. Connect Git Provider"
          description="Create a project-bound GitHub App or GitLab OAuth integration."
        >
          <div className="space-y-5">
            <div className="space-y-3 rounded-[20px] bg-[#f8fbff] p-4">
              <p className="text-sm font-semibold text-[#17385d]">GitHub App</p>
              <Field label="Integration name" value={githubName} onChange={setGithubName} />
              <Field
                label="Installation ID"
                value={githubInstallationId}
                onChange={setGithubInstallationId}
                placeholder="Optional override"
              />
              <ActionButton label="Connect GitHub" onClick={connectGitHub} disabled={loading || !projectId.trim()} />
            </div>

            <div className="space-y-3 rounded-[20px] bg-[#fffaf0] p-4">
              <p className="text-sm font-semibold text-[#17385d]">GitLab OAuth</p>
              <Field label="Integration name" value={gitlabName} onChange={setGitlabName} />
              <Field
                label="GitLab base URL"
                value={gitlabBaseUrl}
                onChange={setGitlabBaseUrl}
                placeholder="https://gitlab.com"
              />
              <ActionButton label="Start GitLab OAuth" onClick={startGitLab} disabled={loading || !projectId.trim()} />
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
          </div>
        </Panel>

        <Panel
          title="2. Sync And Choose Repository"
          description="Sync repositories from a connected integration, then select the repo that should power sandbox runs."
        >
          <div className="space-y-4">
            {state?.integrations.length ? (
              state.integrations.map((integration) => (
                <div key={integration.integration.id} className="rounded-[20px] border border-[rgba(17,24,39,0.08)] p-4">
                  <div className="flex items-start justify-between gap-4">
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
                    />
                  </div>
                  {integration.repositories.length ? (
                    <ul className="mt-3 space-y-2 text-sm text-[#35547d]">
                      {integration.repositories.map((repository) => (
                        <li key={repository.id}>
                          <label className="flex items-center gap-3">
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
                    <p className="mt-3 text-sm text-[#746d66]">No repositories synced yet.</p>
                  )}
                </div>
              ))
            ) : (
              <p className="text-sm text-[#746d66]">Connect a provider first, then sync repositories here.</p>
            )}
          </div>
        </Panel>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Panel
          title="3. Add Runtime Secrets"
          description="Store runtime secrets in AWS Secrets Manager and keep only metadata in the platform database."
        >
          <div className="space-y-4">
            <Field label="Secret label" value={secretLabel} onChange={setSecretLabel} />
            <Field label="Description" value={secretDescription} onChange={setSecretDescription} />
            <Field
              label="Secret value"
              value={secretValue}
              onChange={setSecretValue}
              type="password"
              placeholder="Paste the secret value"
            />
            <ActionButton label="Store secret" onClick={addSecret} disabled={loading || !secretValue.trim()} />
            {state?.secret_refs.length ? (
              <ul className="space-y-2 text-sm text-[#35547d]">
                {state.secret_refs.map((secretRef) => (
                  <li key={secretRef.id}>
                    {secretRef.label} · stored in {secretRef.backend}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-[#746d66]">No project secrets have been added yet.</p>
            )}
          </div>
        </Panel>

        <Panel
          title="4. Create Repo Profile"
          description="Define how the sandbox installs dependencies, reproduces the issue, verifies the fix, and mounts secrets."
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
            <ul className="mt-4 space-y-2 text-sm text-[#35547d]">
              {state.repo_profiles.map((profile) => (
                <li key={profile.id}>
                  {profile.runtime_kind} · verify <code>{profile.verify_command}</code>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-[#746d66]">No repo profile has been created yet.</p>
          )}
        </Panel>
      </section>

      <Panel
        title="Current Onboarding State"
        description="This view comes from the new project-centered onboarding API, so the UI can refresh the full setup state after each action."
      >
        {state ? (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-3">
              <div className="rounded-[20px] bg-[#f8fbff] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">Next steps</p>
                <ul className="mt-3 space-y-2 text-sm text-[#35547d]">
                  {state.suggested_next_steps.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="space-y-3">
              <MiniStat label="Integrations" value={String(state.integrations.length)} />
              <MiniStat label="Repositories" value={String(repositories.length)} />
              <MiniStat label="Secrets" value={String(state.secret_refs.length)} />
              <MiniStat label="Repo profiles" value={String(state.repo_profiles.length)} />
            </div>
          </div>
        ) : (
          <p className="text-sm text-[#746d66]">Bootstrap a project to begin the secure onboarding flow.</p>
        )}
      </Panel>
    </div>
  );
}

function Panel({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="vault-panel-strong rounded-[24px] p-6">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8a8178]">Secure onboarding</p>
      <h2 className="mt-2 text-xl font-semibold text-[#171717]">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-[#746d66]">{description}</p>
      <div className="mt-5">{children}</div>
    </section>
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
        className="w-full rounded-[16px] border border-[rgba(17,24,39,0.12)] bg-white px-4 py-3 text-sm text-[#171717] outline-none transition focus:border-[rgba(52,81,209,0.42)]"
      />
    </label>
  );
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="block">
      <span className="mb-2 block text-sm font-medium text-[#171717]">{label}</span>
      <div className="w-full rounded-[16px] border border-[rgba(17,24,39,0.12)] bg-[#f8fbff] px-4 py-3 text-sm text-[#171717]">
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
        className="w-full rounded-[16px] border border-[rgba(17,24,39,0.12)] bg-white px-4 py-3 text-sm text-[#171717] outline-none transition focus:border-[rgba(52,81,209,0.42)]"
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
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center justify-center rounded-[16px] bg-[#17385d] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1f4a78] disabled:cursor-not-allowed disabled:opacity-60"
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
    <div className="rounded-[20px] bg-[#f8fbff] px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-[#171717]">{value}</p>
    </div>
  );
}
