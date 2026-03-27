"use client";

import type { ReactNode, RefObject } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createPortal } from "react-dom";

import type {
  AuthSession,
  GitHubAppInstallStartResponse,
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

type SecretDraft = {
  id: string;
  label: string;
  value: string;
};

function createSecretDraft(): SecretDraft {
  return {
    id: `secret-draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    label: "",
    value: "",
  };
}

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

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function toProjectSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function ProjectOnboardingConsole() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null>(null);
  const [projectId, setProjectId] = useState("");
  const [state, setState] = useState<ProjectOnboarding | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [gitlabName, setGitlabName] = useState("");
  const [gitlabBaseUrl, setGitlabBaseUrl] = useState("");
  const [lastGitLabAuthUrl, setLastGitLabAuthUrl] = useState<string | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<"github" | "gitlab">("github");

  const [secretDrafts, setSecretDrafts] = useState<SecretDraft[]>([createSecretDraft()]);
  const [openSecretMenuId, setOpenSecretMenuId] = useState<string | null>(null);

  const [runtimeKind, setRuntimeKind] = useState<"python" | "node" | "generic" | "container">("python");
  const [baseImage, setBaseImage] = useState("");
  const [installCommand, setInstallCommand] = useState("");
  const [reproduceCommand, setReproduceCommand] = useState("");
  const [verifyCommand, setVerifyCommand] = useState("");
  const [networkAllowlist, setNetworkAllowlist] = useState("");
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [selectedSecretRefId, setSelectedSecretRefId] = useState("");
  const [secretMountAs, setSecretMountAs] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [serviceType, setServiceType] = useState<
    "frontend" | "backend" | "api" | "worker" | "cron" | "gateway" | "database" | "cache" | "other"
  >("frontend");
  const [selectedServiceRepoProfileId, setSelectedServiceRepoProfileId] = useState("");
  const [serviceOwner, setServiceOwner] = useState("");
  const [serviceDeployTarget, setServiceDeployTarget] = useState("");
  const [serviceRoutingNames, setServiceRoutingNames] = useState("");
  const [servicePathPrefixes, setServicePathPrefixes] = useState("");
  const [serviceDomains, setServiceDomains] = useState("");
  const [serviceTags, setServiceTags] = useState("");
  const [serviceHealthcheckCommand, setServiceHealthcheckCommand] = useState("");
  const [serviceHealthcheckUrl, setServiceHealthcheckUrl] = useState("");
  const [selectedDependencyIds, setSelectedDependencyIds] = useState<string[]>([]);
  const [activeStep, setActiveStep] = useState<(typeof STEP_ORDER)[number]>("1");
  const stepRefs = useRef<Record<string, HTMLElement | null>>({});

  const repositories = useMemo<ProviderRepository[]>(() => {
    if (!state) {
      return [];
    }
    return state.integrations.flatMap((integration) => integration.repositories);
  }, [state]);
  const githubIntegration = useMemo(
    () => state?.integrations.find((integration) => integration.integration.provider === "github") ?? null,
    [state],
  );
  const gitlabIntegration = useMemo(
    () => state?.integrations.find((integration) => integration.integration.provider === "gitlab") ?? null,
    [state],
  );
  const selectedProviderIntegration =
    selectedProvider === "github" ? githubIntegration : gitlabIntegration;
  const newProjectSlug = useMemo(() => toProjectSlug(newProjectName), [newProjectName]);
  const serviceSlug = useMemo(() => toProjectSlug(serviceName), [serviceName]);
  const createRequested = searchParams.get("create") === "1";
  const [createMode, setCreateMode] = useState(createRequested);
  const [bootstrappingPage, setBootstrappingPage] = useState(!createRequested);
  const currentProject = useMemo(
    () => session?.projects.find((project) => project.id === projectId) ?? session?.projects[0] ?? null,
    [projectId, session],
  );

  useEffect(() => {
    setCreateMode(createRequested);
    setBootstrappingPage(!createRequested);
  }, [createRequested]);

  const loadOnboardingState = useCallback(async (bootstrap = false, overrideProjectId?: string) => {
    const resolvedProjectId = (overrideProjectId ?? projectId).trim();
    if (!resolvedProjectId) {
      return;
    }
    const encodedProjectId = encodeURIComponent(resolvedProjectId);
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
    const selectedSecretStillExists = payload.secret_refs.some((secretRef) => secretRef.id === selectedSecretRefId);
    if (!selectedSecretStillExists) {
      const fallbackSecretRef = payload.secret_refs[0];
      setSelectedSecretRefId(fallbackSecretRef?.id ?? "");
      setSecretMountAs(fallbackSecretRef?.label ?? "");
    }
  }, [projectId, selectedRepositoryId, selectedSecretRefId]);

  useEffect(() => {
    if (
      searchParams.get("provider") !== "github" ||
      searchParams.get("provider_status") !== "connected"
    ) {
      return;
    }

    const redirectedProjectId = searchParams.get("project_id")?.trim() ?? "";
    if (redirectedProjectId) {
      setProjectId(redirectedProjectId);
      void loadOnboardingState(false, redirectedProjectId).catch((error) => {
        setErrorMessage(error instanceof Error ? error.message : "Unable to refresh onboarding.");
      });
    }

    setSelectedProvider("github");
    setErrorMessage(null);

    const nextParams = new URLSearchParams(searchParams.toString());
    [
      "provider",
      "provider_status",
      "project_id",
      "integration_id",
      "installation_id",
      "setup_action",
      "synced_repositories",
      "step",
    ].forEach((key) => nextParams.delete(key));
    const nextUrl = nextParams.size > 0 ? `/onboarding?${nextParams.toString()}` : "/onboarding";
    router.replace(nextUrl, { scroll: false });
  }, [loadOnboardingState, router, searchParams]);

  useEffect(() => {
    async function loadSession() {
      try {
        setBootstrappingPage(!createMode);
        const response = await fetch("/api/auth/session", {
          method: "GET",
        });
        if (!response.ok) {
          throw new Error("Unable to load session.");
        }
        const payload = (await response.json()) as Omit<AuthSession, "access_token">;
        const normalized = { ...payload, access_token: "" } as AuthSession;
        setSession(normalized);
        const selectedProjectId = readCookieValue("stimpact_current_project");
        const preferredProject =
          payload.projects.find((project) => project.id === selectedProjectId) ?? payload.projects[0] ?? null;
        if (!createMode && preferredProject?.id) {
          setProjectId(preferredProject.id);
          return;
        }
        setBootstrappingPage(false);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "Unable to load session.");
        setBootstrappingPage(false);
      }
    }
    void loadSession();
  }, [createMode]);

  useEffect(() => {
    if (!projectId.trim()) {
      setBootstrappingPage(false);
      return;
    }
    setBootstrappingPage(true);
    void loadOnboardingState(false).catch((error) => {
      setErrorMessage(error instanceof Error ? error.message : "Unable to load onboarding.");
    }).finally(() => {
      setBootstrappingPage(false);
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
    void successMessage;
    setLoading(true);
    setErrorMessage(null);
    try {
      await action();
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

  async function startGitHubInstall() {
    setLoading(true);
    setErrorMessage(null);
    try {
      const redirectUrl = new URL("/onboarding", window.location.origin);
      redirectUrl.searchParams.set("provider", "github");
      redirectUrl.searchParams.set("step", "3");
      redirectUrl.searchParams.set("project_id", projectId.trim());
      const response = await requestJson<GitHubAppInstallStartResponse>(
        `projects/${encodeURIComponent(projectId.trim())}/provider-integrations/github-app/start`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            name: currentProject ? `${currentProject.name} GitHub` : "GitHub",
            redirect_url: redirectUrl.toString(),
          }),
        },
      );
      window.location.assign(response.installation_url);
    } catch (caughtError) {
      setErrorMessage(
        caughtError instanceof Error ? caughtError.message : "Unable to start GitHub installation.",
      );
      setLoading(false);
    }
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

  function addSecretDraft() {
    setSecretDrafts((current) => [...current, createSecretDraft()]);
    setOpenSecretMenuId(null);
  }

  function updateSecretDraft(
    draftId: string,
    field: keyof Pick<SecretDraft, "label" | "value">,
    nextValue: string,
  ) {
    setSecretDrafts((current) =>
      current.map((draft) => (draft.id === draftId ? { ...draft, [field]: nextValue } : draft)),
    );
  }

  function removeSecretDraft(draftId: string) {
    setSecretDrafts((current) => {
      if (current.length <= 1 && !(state?.secret_refs.length)) {
        return current.map((draft) =>
          draft.id === draftId
            ? {
                ...draft,
                label: "",
                value: "",
              }
            : draft,
        );
      }
      return current.filter((draft) => draft.id !== draftId);
    });
  }

  async function addSecret(draftId: string) {
    const draft = secretDrafts.find((item) => item.id === draftId);
    if (!draft) {
      return;
    }
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/secret-refs`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            label: draft.label,
            value: draft.value,
          }),
        },
      );
      setSecretDrafts((current) => current.filter((item) => item.id !== draftId));
      setOpenSecretMenuId(null);
      await loadOnboardingState(false);
    }, "Secret stored in AWS Secrets Manager.");
  }

  async function deleteSecret(secretRefId: string, secretProjectId: string) {
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(secretProjectId.trim())}/secret-refs/${encodeURIComponent(secretRefId)}`,
        {
          method: "DELETE",
        },
      );
      setOpenSecretMenuId(null);
      if (projectId !== secretProjectId) {
        setProjectId(secretProjectId);
      }
      await loadOnboardingState(false, secretProjectId);
    }, "Secret deleted from AWS Secrets Manager.");
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

  async function createProjectService() {
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/services`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            name: serviceName,
            slug: serviceSlug,
            service_type: serviceType,
            repo_profile_id: selectedServiceRepoProfileId || null,
            owner: serviceOwner || null,
            deploy_target: serviceDeployTarget || null,
            routing_hints: {
              service_names: serviceRoutingNames
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
              path_prefixes: servicePathPrefixes
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
              domains: serviceDomains
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
              tags: serviceTags
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
            },
            sandbox_healthcheck_command: serviceHealthcheckCommand || null,
            sandbox_healthcheck_url: serviceHealthcheckUrl || null,
            dependencies: selectedDependencyIds.map((id) => ({
              depends_on_service_id: id,
              dependency_kind: "required",
            })),
          }),
        },
      );
      setServiceName("");
      setSelectedDependencyIds([]);
      setServiceOwner("");
      setServiceDeployTarget("");
      setServiceRoutingNames("");
      setServicePathPrefixes("");
      setServiceDomains("");
      setServiceTags("");
      setServiceHealthcheckCommand("");
      setServiceHealthcheckUrl("");
      if (!selectedServiceRepoProfileId && state?.repo_profiles[0]?.id) {
        setSelectedServiceRepoProfileId(state.repo_profiles[0].id);
      }
      await loadOnboardingState(false);
    }, "Project service configured.");
  }

  async function createFirstProject() {
    setCreatingProject(true);
    setErrorMessage(null);
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
      await fetch("/api/projects/current", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ project_id: payload.id }),
      });
      setProjectId(payload.id);
      setCreateMode(false);
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
  const hasProjectServices = (state?.project_services.length ?? 0) > 0;

  if (bootstrappingPage && !createMode) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center px-6">
        <div className="flex flex-col items-center gap-3 text-center">
          <span className="inline-flex h-9 w-9 animate-spin rounded-full border-2 border-[rgba(23,56,93,0.18)] border-t-[rgba(255,106,61,0.88)]" />
          <p className="text-sm font-medium text-[#746d66]">Loading..</p>
        </div>
      </div>
    );
  }

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
            provider, add secrets, define repo profiles, and map the deployable
            services that power sandbox verification.
          </p>

          <OnboardingTimeline
            activeStep={activeStep}
            onStepSelect={(step) => {
              const node = stepRefs.current[step];
              if (!node) {
                return;
              }
              node.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
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
                label: "Services",
                detail: "Map infrastructure",
                complete: hasRepoProfiles && hasProjectServices,
              },
            ]}
          />

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
          {hasProject && !createMode ? (
            <>
              <div className="grid gap-4 lg:grid-cols-2">
                <ReadOnlyField label="Workspace" value={session?.organization.name ?? "Workspace"} />
                <ReadOnlyField label="Project" value={projectId} />
              </div>
              <p className="mt-4 text-sm leading-6 text-[#5f6470]">
                Your onboarding actions are scoped to the authenticated workspace and
                selected project.
              </p>
              <p className="mt-2 text-sm leading-6 text-[#8a8178]">
                Use the project switcher in the workspace shell to return here and create another
                project when needed.
              </p>
            </>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-4">
                <Field
                  label="Project name"
                  value={newProjectName}
                  onChange={setNewProjectName}
                  placeholder="Production"
                  helperText={
                    newProjectSlug
                      ? `Slug auto-generated as ${newProjectSlug}`
                      : "Slug auto-generated from the project name"
                  }
                />
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
          description="Choose the provider you want to connect first, then sync repositories from that integration."
          complete={hasIntegrations}
          sectionRef={(node) => {
            stepRefs.current["2"] = node;
          }}
        >
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <ProviderChoiceCard
                label="GitHub"
                description={
                  githubIntegration
                    ? `${readIntegrationAccount(githubIntegration)} connected · ${githubIntegration.repositories.length} repos available`
                    : "Connect a GitHub App installation and sync repositories."
                }
                statusLabel={githubIntegration ? "Connected" : undefined}
                connected={Boolean(githubIntegration)}
                subdued={!githubIntegration && Boolean(selectedProviderIntegration)}
                active={selectedProvider === "github"}
                onClick={() => setSelectedProvider("github")}
                icon={<GitHubGlyph />}
              />
              <ProviderChoiceCard
                label="GitLab"
                description={
                  gitlabIntegration
                    ? `${readIntegrationAccount(gitlabIntegration)} connected · ${gitlabIntegration.repositories.length} repos available`
                    : "Start a GitLab OAuth flow and sync repositories."
                }
                statusLabel={gitlabIntegration ? "Connected" : undefined}
                connected={Boolean(gitlabIntegration)}
                subdued={!gitlabIntegration && Boolean(selectedProviderIntegration)}
                active={selectedProvider === "gitlab"}
                onClick={() => setSelectedProvider("gitlab")}
                icon={<GitLabGlyph />}
              />
            </div>

            {selectedProviderIntegration ? (
              <div className="overflow-hidden rounded-[24px] border border-[rgba(22,101,52,0.18)] bg-white shadow-[0_18px_36px_rgba(34,197,94,0.08)]">
                <div className="flex items-center justify-between gap-4 border-b border-[rgba(22,101,52,0.14)] bg-[linear-gradient(180deg,rgba(240,253,244,0.98),rgba(231,248,237,0.98))] px-5 py-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-[16px] border border-[rgba(22,101,52,0.2)] bg-[linear-gradient(180deg,#f0fdf4,#dcfce7)] text-[#15803d]">
                      {selectedProvider === "github" ? <GitHubGlyph /> : <GitLabGlyph />}
                    </div>
                    <div>
                      <p className="text-base font-semibold text-[#171717]">
                        {selectedProvider === "github" ? "GitHub connected" : "GitLab connected"}
                      </p>
                      <p className="mt-1 text-sm text-[#746d66]">
                        {selectedProvider === "github"
                          ? "Connected and ready for repository selection."
                          : "Connected and ready for repository selection."}
                      </p>
                    </div>
                  </div>
                  <span className="inline-flex rounded-full bg-[linear-gradient(180deg,#22c55e,#16a34a)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-white shadow-[0_10px_20px_rgba(34,197,94,0.22)]">
                    Connected
                  </span>
                </div>
                <div className="grid gap-5 px-5 py-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                  <div className="grid gap-4 sm:grid-cols-3">
                    <ConnectionDetail
                      label="Account"
                      value={readIntegrationAccount(selectedProviderIntegration)}
                    />
                    <ConnectionDetail
                      label="Integration"
                      value={selectedProviderIntegration.integration.name}
                    />
                    <ConnectionDetail
                      label="Repositories ready"
                      value={String(selectedProviderIntegration.repositories.length)}
                      emphasize
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <ActionButton
                      label={selectedProvider === "github" ? "Reconnect GitHub" : "Reconnect GitLab"}
                      onClick={selectedProvider === "github" ? startGitHubInstall : startGitLab}
                      disabled={loading || !hasProject}
                      variant="secondary"
                    />
                    <a
                      href="#onboarding-step-3"
                      className="inline-flex text-sm font-semibold text-[#3451d1] hover:underline"
                    >
                      Continue to repository selection
                    </a>
                  </div>
                </div>
              </div>
            ) : selectedProvider === "github" ? (
              <SubStepCard title="GitHub App" tone="warm">
                <p className="text-sm leading-6 text-[#65584f]">
                  Connect GitHub in one step. We will open the GitHub App install flow, return you
                  here automatically, sync the available repositories, and let you pick the repo to
                  map next.
                </p>
                <ActionButton
                  label="Connect GitHub"
                  onClick={startGitHubInstall}
                  disabled={loading || !hasProject}
                />
              </SubStepCard>
            ) : (
              <SubStepCard title="GitLab OAuth" tone="warm">
                <Field
                  label="Integration name"
                  value={gitlabName}
                  onChange={setGitlabName}
                  placeholder="Acme GitLab"
                />
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
            )}
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
                <div key={integration.integration.id} className="space-y-4">
                  <div className="flex flex-col gap-4 border-b border-[rgba(29,26,24,0.08)] pb-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-[14px] border border-[rgba(34,197,94,0.22)] bg-[linear-gradient(180deg,#f0fdf4,#dcfce7)] text-[#16a34a]">
                        {integration.integration.provider === "github" ? <GitHubGlyph /> : <GitLabGlyph />}
                      </div>
                      <div>
                        <p className="font-semibold text-[#171717]">{integration.integration.name}</p>
                        <p className="mt-1 text-sm text-[#746d66]">
                          {readIntegrationAccount(integration)} · {integration.repositories.length} synced repos
                        </p>
                      </div>
                    </div>
                    <ActionButton
                      label="Refresh repos"
                      onClick={() => syncRepositories(integration.integration.id)}
                      disabled={loading}
                      variant="secondary"
                    />
                  </div>
                  {integration.repositories.length ? (
                    <ul className="grid gap-3 text-sm text-[#35547d]">
                      {integration.repositories.map((repository) => (
                        <li key={repository.id}>
                          <label
                            className={`flex cursor-pointer items-center justify-between gap-4 rounded-[18px] border px-4 py-4 transition ${
                              selectedRepositoryId === repository.id
                                ? "border-[rgba(22,101,52,0.28)] bg-[linear-gradient(180deg,#f0fdf4,#dcfce7)] shadow-[0_12px_28px_rgba(34,197,94,0.14)]"
                                : "border-[rgba(29,26,24,0.08)] bg-white hover:border-[rgba(255,106,61,0.24)] hover:bg-[rgba(255,248,242,0.98)]"
                            }`}
                          >
                            <div className="flex items-center gap-3">
                              <span
                                className={`flex h-5 w-5 items-center justify-center rounded-full border ${
                                  selectedRepositoryId === repository.id
                                    ? "border-[#16a34a] bg-[#16a34a]"
                                    : "border-[rgba(29,26,24,0.18)] bg-white"
                                }`}
                              >
                                <span className="h-2.5 w-2.5 rounded-full bg-white" />
                              </span>
                              <input
                                type="radio"
                                name="provider_repository_id"
                                checked={selectedRepositoryId === repository.id}
                                onChange={() => setSelectedRepositoryId(repository.id)}
                                className="sr-only"
                              />
                              <span>
                                <span className="block font-semibold text-[#171717]">
                                  {repository.owner}/{repository.name}
                                </span>
                                <span className="mt-1 block text-sm text-[#746d66]">
                                  Default branch {repository.default_branch}
                                </span>
                              </span>
                            </div>
                            <span
                              className={`inline-flex rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${
                                selectedRepositoryId === repository.id
                                  ? "bg-[linear-gradient(180deg,#22c55e,#16a34a)] text-white"
                                  : "bg-[rgba(29,26,24,0.06)] text-[#7c756d]"
                              }`}
                            >
                              {selectedRepositoryId === repository.id ? "Selected" : "Choose"}
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
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-semibold text-[#171717]">Project secrets</p>
                <p className="mt-1 text-sm text-[#746d66]">
                  Add environment secrets, then manage them from the list below.
                </p>
              </div>
              <button
                type="button"
                onClick={addSecretDraft}
                className="inline-flex items-center gap-2 self-start rounded-full border border-[rgba(29,26,24,0.1)] bg-white px-3 py-2 text-sm font-semibold text-[#171717] transition hover:border-[rgba(255,106,61,0.22)] hover:bg-[#fff9f5]"
              >
                <PlusMiniGlyph />
                Add secret
              </button>
            </div>

            {secretDrafts.length ? (
              <div className="rounded-[24px] border border-[rgba(29,26,24,0.08)] bg-[rgba(255,255,255,0.82)] p-5 shadow-[0_12px_28px_rgba(15,23,42,0.04)]">
                <div className="space-y-5">
                  {secretDrafts.map((draft, index) => (
                    <div
                      key={draft.id}
                      className={index < secretDrafts.length - 1 ? "border-b border-[rgba(29,26,24,0.08)] pb-5" : ""}
                    >
                      <input
                        type="text"
                        name={`decoy-username-${draft.id}`}
                        autoComplete="username"
                        tabIndex={-1}
                        aria-hidden="true"
                        className="hidden"
                      />
                      <input
                        type="password"
                        name={`decoy-password-${draft.id}`}
                        autoComplete="new-password"
                        tabIndex={-1}
                        aria-hidden="true"
                        className="hidden"
                      />
                      <div className="grid gap-4 md:grid-cols-2">
                        <Field
                          label="Secret key"
                          value={draft.label}
                          onChange={(value) => updateSecretDraft(draft.id, "label", value)}
                          placeholder="VITE_SUPABASE_URL"
                          name={`secret-key-${draft.id}`}
                          suppressPasswordManagers
                        />
                        <Field
                          label="Secret value"
                          value={draft.value}
                          onChange={(value) => updateSecretDraft(draft.id, "value", value)}
                          type="password"
                          placeholder="Paste the secret value"
                          name={`secret-value-${draft.id}`}
                          suppressPasswordManagers
                        />
                      </div>
                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        <ActionButton
                          label="Store secret"
                          onClick={() => {
                            void addSecret(draft.id);
                          }}
                          disabled={loading || !draft.label.trim() || !draft.value.trim()}
                          variant="success"
                        />
                        <ActionButton
                          label="Cancel"
                          onClick={() => removeSecretDraft(draft.id)}
                          variant="secondary"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {state?.secret_refs.length ? (
              <div className="overflow-visible rounded-[24px] border border-[rgba(29,26,24,0.08)] bg-[rgba(255,255,255,0.8)]">
                {state.secret_refs.map((secretRef, index) => (
                  <SecretManagerRow
                    key={secretRef.id}
                    secretRef={secretRef}
                    menuOpen={openSecretMenuId === secretRef.id}
                    showBorder={index < state.secret_refs.length - 1}
                    onToggleMenu={() =>
                      setOpenSecretMenuId((current) => (current === secretRef.id ? null : secretRef.id))
                    }
                    onDelete={() => {
                      void deleteSecret(secretRef.id, secretRef.project_id);
                    }}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-[#746d66]">
                No project secrets have been added yet. Add one here to continue configuring repo profiles.
              </p>
            )}
          </div>
        </StepPanel>

        <StepPanel
          step="05"
          stepKey="5"
          title="Create repo profiles and map services"
          description="Define sandbox commands, then turn those repo profiles into named project services with routing hints and dependencies."
          complete={hasRepoProfiles && hasProjectServices}
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
            <Field
              label="Base image"
              value={baseImage}
              onChange={setBaseImage}
              placeholder="public.ecr.aws/docker/library/python:3.12"
            />
            <Field
              label="Install command"
              value={installCommand}
              onChange={setInstallCommand}
              placeholder="pip install -r requirements.txt"
              className="md:col-span-2"
            />
            <Field
              label="Reproduce command"
              value={reproduceCommand}
              onChange={setReproduceCommand}
              placeholder="pytest"
              className="md:col-span-2"
            />
            <Field
              label="Verify command"
              value={verifyCommand}
              onChange={setVerifyCommand}
              placeholder="pytest"
              className="md:col-span-2"
            />
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

          <div className="mt-6 rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.82)] p-5">
            <div className="flex flex-col gap-2">
              <p className="text-sm font-semibold text-[#171717]">Map deployable services</p>
              <p className="text-sm leading-6 text-[#746d66]">
                Give each connected application surface a clear service identity, attach it to a
                repo profile, and define which services must be available together.
              </p>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <Field
                label="Service name"
                value={serviceName}
                onChange={setServiceName}
                placeholder="Web client"
                helperText={serviceSlug ? `Slug auto-generated as ${serviceSlug}` : "Slug auto-generated from the service name"}
              />
              <SelectField
                label="Service type"
                value={serviceType}
                onChange={(value) =>
                  setServiceType(
                    value as
                      | "frontend"
                      | "backend"
                      | "api"
                      | "worker"
                      | "cron"
                      | "gateway"
                      | "database"
                      | "cache"
                      | "other",
                  )
                }
                options={[
                  { value: "frontend", label: "Frontend" },
                  { value: "backend", label: "Backend" },
                  { value: "api", label: "API" },
                  { value: "worker", label: "Worker" },
                  { value: "cron", label: "Cron" },
                  { value: "gateway", label: "Gateway" },
                  { value: "database", label: "Database" },
                  { value: "cache", label: "Cache" },
                  { value: "other", label: "Other" },
                ]}
              />
              <SelectField
                label="Repo profile"
                value={selectedServiceRepoProfileId}
                onChange={setSelectedServiceRepoProfileId}
                options={[
                  { value: "", label: "Choose a repo profile" },
                  ...(state?.repo_profiles.map((profile) => ({
                    value: profile.id,
                    label: `${profile.runtime_kind} · ${profile.verify_command}`,
                  })) ?? []),
                ]}
              />
              <Field
                label="Owner"
                value={serviceOwner}
                onChange={setServiceOwner}
                placeholder="Platform team"
              />
              <Field
                label="Deploy target"
                value={serviceDeployTarget}
                onChange={setServiceDeployTarget}
                placeholder="Production web"
              />
              <Field
                label="Telemetry service names"
                value={serviceRoutingNames}
                onChange={setServiceRoutingNames}
                placeholder="web, app-frontend"
              />
              <Field
                label="Path prefixes"
                value={servicePathPrefixes}
                onChange={setServicePathPrefixes}
                placeholder="src/app, web/"
              />
              <Field
                label="Domains"
                value={serviceDomains}
                onChange={setServiceDomains}
                placeholder="app.example.com"
              />
              <Field
                label="Tags"
                value={serviceTags}
                onChange={setServiceTags}
                placeholder="react, customer-facing"
              />
              <Field
                label="Healthcheck command"
                value={serviceHealthcheckCommand}
                onChange={setServiceHealthcheckCommand}
                placeholder="curl -f http://localhost:3000/health"
                className="md:col-span-2"
              />
              <Field
                label="Healthcheck URL"
                value={serviceHealthcheckUrl}
                onChange={setServiceHealthcheckUrl}
                placeholder="http://localhost:3000/health"
                className="md:col-span-2"
              />
            </div>

            {state?.project_services.length ? (
              <div className="mt-5 rounded-[20px] border border-[rgba(17,24,39,0.06)] bg-[#f8fbff] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">
                  Dependencies
                </p>
                <div className="mt-3 grid gap-2">
                  {state.project_services.map((service) => (
                    <label
                      key={service.id}
                      className="flex items-center gap-3 rounded-[16px] border border-[rgba(17,24,39,0.06)] bg-white px-4 py-3 text-sm text-[#35547d]"
                    >
                      <input
                        type="checkbox"
                        checked={selectedDependencyIds.includes(service.id)}
                        onChange={() =>
                          setSelectedDependencyIds((current) =>
                            current.includes(service.id)
                              ? current.filter((item) => item !== service.id)
                              : [...current, service.id],
                          )
                        }
                      />
                      <span>
                        {service.name} · {service.service_type}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-4">
              <ActionButton
                label="Add project service"
                onClick={createProjectService}
                disabled={loading || !serviceName.trim() || !serviceSlug.trim() || !selectedServiceRepoProfileId}
              />
            </div>

            {state?.project_services.length ? (
              <div className="mt-4 grid gap-3">
                {state.project_services.map((service) => (
                  <div
                    key={service.id}
                    className="rounded-[18px] border border-[rgba(17,24,39,0.08)] bg-white px-4 py-4"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-[#171717]">{service.name}</p>
                      <span className="rounded-full bg-[rgba(255,106,61,0.12)] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#d45a2b]">
                        {service.service_type}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[#746d66]">
                      Repo profile:{" "}
                      {state.repo_profiles.find((profile) => profile.id === service.repo_profile_id)?.verify_command ??
                        "Unmapped"}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-[#746d66]">
                      Routing hints:{" "}
                      {[
                        ...service.routing_hints.service_names,
                        ...service.routing_hints.path_prefixes,
                        ...service.routing_hints.domains,
                      ].join(", ") || "No routing hints yet"}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-[#746d66]">
                      Dependencies:{" "}
                      {service.dependencies.length
                        ? service.dependencies
                            .map((dependency) => {
                              const target = state.project_services.find(
                                (candidate) => candidate.id === dependency.depends_on_service_id,
                              );
                              return target?.name ?? dependency.depends_on_service_id;
                            })
                            .join(", ")
                        : "None"}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-[#746d66]">
                No project services have been mapped yet.
              </p>
            )}
          </div>
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
              <MiniStat label="Services" value={String(state?.project_services.length ?? 0)} />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function readCookieValue(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const match = document.cookie
    .split("; ")
    .find((value) => value.startsWith(`${name}=`));
  if (!match) {
    return null;
  }
  const [, cookieValue] = match.split("=", 2);
  return cookieValue ? decodeURIComponent(cookieValue) : null;
}

function readIntegrationAccount(integration: ProjectOnboarding["integrations"][number]): string {
  const accountLogin =
    typeof integration.integration.metadata.account_login === "string"
      ? integration.integration.metadata.account_login
      : typeof integration.integration.metadata.connected_account_login === "string"
        ? integration.integration.metadata.connected_account_login
        : null;
  return accountLogin?.trim() ? accountLogin : "Connected account";
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
      className="relative scroll-mt-24 overflow-hidden rounded-[28px] border border-[rgba(29,26,24,0.1)] bg-[linear-gradient(180deg,rgba(255,251,247,0.98),rgba(249,242,234,0.98))] px-6 py-6 shadow-[0_18px_40px_rgba(15,23,42,0.06)] lg:scroll-mt-28"
    >
      <div
        className={`absolute left-0 top-0 h-full w-1.5 opacity-95 ${
          complete
            ? "bg-[linear-gradient(180deg,#4ade80_0%,#22c55e_42%,#15803d_100%)]"
            : "bg-[linear-gradient(180deg,#ffb253_0%,#ff6a3d_42%,#ff5a2a_100%)]"
        }`}
      />
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

function ConnectionDetail({
  label,
  value,
  emphasize = false,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8a8178]">{label}</p>
      <p className={`text-base font-semibold ${emphasize ? "text-[#15803d]" : "text-[#171717]"}`}>
        {value}
      </p>
    </div>
  );
}

function ProviderChoiceCard({
  label,
  description,
  statusLabel,
  connected,
  subdued,
  active,
  onClick,
  icon,
}: {
  label: string;
  description: string;
  statusLabel?: string;
  connected?: boolean;
  subdued?: boolean;
  active?: boolean;
  onClick: () => void;
  icon: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-start gap-4 rounded-[22px] border px-5 py-5 text-left transition cursor-pointer ${
        connected && active
          ? "border-[rgba(23,23,23,0.22)] bg-white shadow-[0_16px_32px_rgba(15,23,42,0.08)] ring-1 ring-[rgba(23,23,23,0.06)]"
          : subdued
            ? "border-[rgba(29,26,24,0.05)] bg-[rgba(255,255,255,0.62)] opacity-65 hover:opacity-80"
            : active
              ? "border-[rgba(29,26,24,0.18)] bg-white shadow-[0_16px_32px_rgba(15,23,42,0.08)]"
              : "border-[rgba(29,26,24,0.08)] bg-white hover:border-[rgba(29,26,24,0.16)] hover:bg-[rgba(255,255,255,0.96)]"
      }`}
    >
      <div
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-[16px] border ${
          connected && active
            ? "border-[#171717] bg-[#171717] text-white shadow-[0_10px_20px_rgba(23,23,23,0.12)]"
            : active
              ? "border-[rgba(29,26,24,0.12)] bg-[#f7f3ee] text-[#171717]"
              : "border-[rgba(29,26,24,0.08)] bg-[#fbfaf8] text-[#4a423d]"
        }`}
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className={`text-sm font-semibold ${connected && active ? "text-[#171717]" : "text-[#171717]"}`}>
            {label}
          </p>
          {statusLabel ? (
            <span className="inline-flex rounded-full bg-[linear-gradient(180deg,#22c55e,#16a34a)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-white shadow-[0_10px_20px_rgba(34,197,94,0.18)]">
              {statusLabel}
            </span>
          ) : null}
        </div>
        <p className={`mt-1 text-sm leading-6 ${connected && active ? "text-[#5f6470]" : "text-[#746d66]"}`}>
          {description}
        </p>
      </div>
    </button>
  );
}

function GitHubGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-current">
      <path d="M12 .75a11.25 11.25 0 0 0-3.557 21.922c.563.104.768-.244.768-.543 0-.268-.01-.98-.015-1.924-3.123.679-3.783-1.505-3.783-1.505-.51-1.297-1.246-1.642-1.246-1.642-1.019-.697.077-.683.077-.683 1.126.08 1.719 1.156 1.719 1.156 1.001 1.716 2.626 1.22 3.266.933.101-.726.392-1.221.714-1.501-2.493-.284-5.114-1.247-5.114-5.55 0-1.226.438-2.229 1.156-3.014-.116-.285-.501-1.43.109-2.981 0 0 .944-.302 3.094 1.151a10.764 10.764 0 0 1 5.633 0c2.149-1.453 3.092-1.151 3.092-1.151.611 1.551.226 2.696.111 2.981.719.785 1.154 1.788 1.154 3.014 0 4.314-2.625 5.263-5.126 5.542.403.347.762 1.031.762 2.078 0 1.501-.014 2.712-.014 3.082 0 .302.202.652.775.541A11.251 11.251 0 0 0 12 .75Z" />
    </svg>
  );
}

function GitLabGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-current">
      <path d="m12 22.1 4.07-12.53H7.93L12 22.1Z" />
      <path d="M12 22.1 7.93 9.57H2.2L12 22.1Z" opacity="0.78" />
      <path d="M2.2 9.57.96 13.4a.84.84 0 0 0 .3.94L12 22.1 2.2 9.57Z" opacity="0.62" />
      <path d="M2.2 9.57h5.73L5.47 2.04a.42.42 0 0 0-.8 0L2.2 9.57Z" opacity="0.84" />
      <path d="M12 22.1 16.07 9.57h5.73L12 22.1Z" opacity="0.78" />
      <path d="m21.8 9.57 1.24 3.83a.84.84 0 0 1-.3.94L12 22.1 21.8 9.57Z" opacity="0.62" />
      <path d="M21.8 9.57h-5.73l2.46-7.53a.42.42 0 0 1 .8 0l2.47 7.53Z" opacity="0.84" />
    </svg>
  );
}

function OnboardingTimeline({
  steps,
  activeStep,
  onStepSelect,
}: {
  steps: Array<{
    step: (typeof STEP_ORDER)[number];
    label: string;
    detail: string;
    complete: boolean;
  }>;
  activeStep: (typeof STEP_ORDER)[number];
  onStepSelect: (step: (typeof STEP_ORDER)[number]) => void;
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
              complete={item.complete}
              onSelect={onStepSelect}
            />
          ))}
        </div>
      </div>

      <div className="grid gap-3 lg:hidden">
        {steps.map((item) => (
          <button
            key={item.step}
            type="button"
            onClick={() => onStepSelect(item.step)}
            className="flex w-full items-start gap-3 rounded-[18px] border border-[rgba(29,26,24,0.08)] bg-[linear-gradient(180deg,rgba(255,250,246,0.96),rgba(245,239,232,0.98))] px-4 py-3 text-left shadow-[0_8px_24px_rgba(15,23,42,0.04)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_30px_rgba(15,23,42,0.07)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,106,61,0.24)]"
          >
            <TimelineDot
              active={activeStep === item.step}
              complete={item.complete}
              step={item.step}
            />
            <div>
              <p className="text-sm font-semibold text-[#171717]">
                {item.step}. {item.label}
              </p>
              <p className="mt-1 text-xs leading-5 text-[#746d66]">{item.detail}</p>
            </div>
          </button>
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
  complete,
  onSelect,
}: {
  step: string;
  label: string;
  detail: string;
  active: boolean;
  complete: boolean;
  onSelect: (step: (typeof STEP_ORDER)[number]) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(step as (typeof STEP_ORDER)[number])}
      className="group relative w-full cursor-pointer bg-transparent px-1 pt-0 text-center focus:outline-none"
    >
      <div className="mx-auto flex w-full flex-col items-center">
        <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8a8178]">
          Step {step}
        </span>
        <div className="relative z-10 mt-2 flex h-14 items-center justify-center overflow-visible">
          <TimelineDot active={active} complete={complete} step={step} />
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
    </button>
  );
}

function TimelineDot({
  active,
  complete,
  step,
}: {
  active: boolean;
  complete: boolean;
  step: string;
}) {
  return (
    <span
      className={`relative inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-full border text-[11px] font-semibold transition duration-200 ease-out group-hover:-translate-y-0.5 group-hover:scale-[1.05] ${
        complete
          ? "border-[rgba(34,197,94,0.24)] bg-[linear-gradient(180deg,#34d399_0%,#22c55e_52%,#16a34a_100%)] text-white group-hover:shadow-[0_14px_28px_rgba(34,197,94,0.22)]"
          : "border-[rgba(255,106,61,0.24)] bg-[linear-gradient(180deg,#ff9d70_0%,#ff7d4d_56%,#ff6a3d_100%)] text-white/92 group-hover:shadow-[0_14px_28px_rgba(255,106,61,0.18)]"
      } ${
        active ? "shadow-[0_10px_22px_rgba(15,23,42,0.08)]" : ""
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
          ? "bg-[linear-gradient(180deg,#22c55e,#16a34a)] text-white shadow-[0_10px_20px_rgba(34,197,94,0.18)]"
          : "bg-[rgba(255,106,61,0.12)] text-[#9b4c2f]"
      }`}
    >
      {complete ? "Complete" : "In progress"}
    </span>
  );
}

function SecretManagerRow({
  secretRef,
  menuOpen,
  showBorder,
  onToggleMenu,
  onDelete,
}: {
  secretRef: ProjectOnboarding["secret_refs"][number];
  menuOpen: boolean;
  showBorder: boolean;
  onToggleMenu: () => void;
  onDelete: () => void;
}) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  return (
    <div
      className={`relative flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between ${
        showBorder ? "border-b border-[rgba(29,26,24,0.08)]" : ""
      }`}
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-[#171717]">{secretRef.label}</p>
        <p className="mt-1 text-sm text-[#746d66]">Project-wide secret</p>
      </div>
      <div className="flex flex-1 flex-col gap-4 sm:flex-row sm:items-center sm:justify-end sm:gap-8">
        <div className="min-w-[150px]">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">Value</p>
          <p className="mt-2 text-sm tracking-[0.28em] text-[#5f6470]">••••••••••••••••</p>
        </div>
        <div className="min-w-[170px]">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">Updated</p>
          <p className="mt-2 text-sm text-[#5f6470]">{formatSecretTimestamp(secretRef.updated_at)}</p>
        </div>
        <div className="self-start sm:self-auto">
          <button
            ref={buttonRef}
            type="button"
            onClick={onToggleMenu}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(29,26,24,0.08)] bg-white text-[#5f6470] transition hover:border-[rgba(29,26,24,0.14)] hover:text-[#171717]"
            aria-label={`Open actions for ${secretRef.label}`}
          >
            <OverflowMenuGlyph />
          </button>
          {menuOpen ? (
            <SecretActionMenu
              anchorRef={buttonRef}
              label={secretRef.label}
              onDelete={onDelete}
              onRequestClose={onToggleMenu}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function SecretActionMenu({
  anchorRef,
  label,
  onDelete,
  onRequestClose,
}: {
  anchorRef: RefObject<HTMLButtonElement | null>;
  label: string;
  onDelete: () => void;
  onRequestClose: () => void;
}) {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    function updatePosition() {
      const anchor = anchorRef.current;
      if (!anchor || typeof window === "undefined") {
        return;
      }
      const rect = anchor.getBoundingClientRect();
      const menuWidth = 150;
      const viewportPadding = 12;
      const left = Math.min(
        Math.max(viewportPadding, rect.right - menuWidth),
        window.innerWidth - menuWidth - viewportPadding,
      );
      setPosition({
        top: rect.bottom + 8,
        left,
      });
    }

    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || anchorRef.current?.contains(target)) {
        return;
      }
      onRequestClose();
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [anchorRef, onRequestClose]);

  if (typeof document === "undefined" || position === null) {
    return null;
  }

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[80] min-w-[150px] rounded-[16px] border border-[rgba(29,26,24,0.08)] bg-white p-2 shadow-[0_18px_36px_rgba(15,23,42,0.12)]"
      style={{ top: `${position.top}px`, left: `${position.left}px` }}
      aria-label={`Actions for ${label}`}
    >
      <button
        type="button"
        onClick={onDelete}
        className="flex w-full items-center rounded-[12px] px-3 py-2 text-left text-sm font-medium text-[#b42318] transition hover:bg-[rgba(180,35,24,0.06)]"
      >
        Delete secret
      </button>
    </div>,
    document.body,
  );
}

function formatSecretTimestamp(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return "Recently updated";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "numeric",
    day: "numeric",
    year: "2-digit",
  }).format(new Date(timestamp));
}

function PlusMiniGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4 fill-none stroke-current stroke-[1.8]">
      <path d="M8 3.25v9.5M3.25 8h9.5" strokeLinecap="round" />
    </svg>
  );
}

function OverflowMenuGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4 fill-current">
      <circle cx="3" cy="8" r="1.2" />
      <circle cx="8" cy="8" r="1.2" />
      <circle cx="13" cy="8" r="1.2" />
    </svg>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  className,
  autoComplete,
  helperText,
  name,
  suppressPasswordManagers = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  className?: string;
  autoComplete?: string;
  helperText?: string;
  name?: string;
  suppressPasswordManagers?: boolean;
}) {
  return (
    <label className={`block ${className ?? ""}`}>
      <span className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-[#171717]">{label}</span>
        {helperText ? (
          <span className="text-[11px] font-medium text-[#8d857d]">{helperText}</span>
        ) : null}
      </span>
      <input
        type={type}
        name={name}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete={suppressPasswordManagers ? (type === "password" ? "new-password" : "off") : autoComplete}
        spellCheck={suppressPasswordManagers ? false : undefined}
        autoCapitalize={suppressPasswordManagers ? "off" : undefined}
        autoCorrect={suppressPasswordManagers ? "off" : undefined}
        data-form-type={suppressPasswordManagers ? "other" : undefined}
        data-lpignore={suppressPasswordManagers ? "true" : undefined}
        data-1p-ignore={suppressPasswordManagers ? "true" : undefined}
        data-bwignore={suppressPasswordManagers ? "true" : undefined}
        data-op-ignore={suppressPasswordManagers ? "true" : undefined}
        data-protonpass-ignore={suppressPasswordManagers ? "true" : undefined}
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
  variant?: "primary" | "secondary" | "success";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center rounded-[16px] px-4 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${
        variant === "secondary"
          ? "border border-[rgba(29,26,24,0.08)] bg-[rgba(255,250,245,0.84)] text-[#17385d] hover:border-[rgba(255,106,61,0.2)] hover:bg-[#fff5ef]"
          : variant === "success"
            ? "bg-[linear-gradient(180deg,#1fbf68_0%,#16a34a_100%)] text-white shadow-[0_14px_28px_rgba(22,163,74,0.18)] hover:-translate-y-0.5 hover:shadow-[0_18px_34px_rgba(22,163,74,0.24)]"
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
