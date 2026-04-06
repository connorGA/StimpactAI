"use client";

import type { ReactNode, RefObject } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createPortal } from "react-dom";

import { useAppShellSession } from "@/components/app-shell";
import type {
  GitHubAppInstallStartResponse,
  GitLabOAuthStartResponse,
  ProjectApiKeyCreateResponse,
  ProjectOnboarding,
  ProjectPolicy,
  ProjectSummary,
  ProviderRepository,
  RepoProfileInference,
  RepoProfile,
  SdkBootstrapChangeRequestResponse,
  SdkBootstrapPlanPreview,
  SdkBootstrapPreview,
  ProjectTelemetryVerification,
} from "@/lib/types";

type ApiErrorPayload = {
  error?: {
    message?: string;
  };
};

const STEP_ORDER = ["1", "2", "3", "4", "5", "6", "7"] as const;
const inFlightOnboardingRequests = new Map<string, Promise<ProjectOnboarding>>();

type SecretDraft = {
  id: string;
  label: string;
  value: string;
};

type RepoSecretMountDraft = {
  id: string;
  secretRefId: string;
  mountAs: string;
};

type StepEditKey = "2" | "3" | "4" | "5" | "6" | "7";

type OnboardingEditorSnapshot = {
  selectedProvider: "github" | "gitlab";
  gitlabName: string;
  gitlabBaseUrl: string;
  lastGitLabAuthUrl: string | null;
  selectedRepositoryId: string;
  secretDrafts: SecretDraft[];
  runtimeKind: "python" | "node" | "generic" | "container";
  baseImage: string;
  installCommand: string;
  reproduceCommand: string;
  verifyCommand: string;
  networkAllowlist: string;
  repoSecretMounts: RepoSecretMountDraft[];
  serviceName: string;
  serviceType:
    | "frontend"
    | "backend"
    | "fullstack"
    | "api"
    | "worker"
    | "cron"
    | "gateway"
    | "database"
    | "cache"
    | "other";
  selectedServiceRepoProfileId: string;
  serviceOwner: string;
  serviceDeployTarget: string;
  serviceRoutingNames: string;
  servicePathPrefixes: string;
  serviceDomains: string;
  serviceTags: string;
  serviceHealthcheckCommand: string;
  serviceHealthcheckUrl: string;
  selectedDependencyIds: string[];
  stepFivePreviewMode: "single" | "multi" | null;
  showStepFiveAdvanced: boolean;
  repoProfileInference: RepoProfileInference | null;
  repoProfileInferenceError: string | null;
  telemetryKeyName: string;
  telemetryKeyPlaintext: string | null;
  sdkEnvironment: string;
  sdkSetupMode: "automatic" | "manual";
  sdkBootstrapPlan: SdkBootstrapPlanPreview | null;
  sdkBootstrapPreview: SdkBootstrapPreview | null;
  selectedSdkStrategyId: string;
  dismissedSdkPreviewStrategyId: string | null;
  sdkAutomaticRequested: boolean;
  sdkAutomationStage: "idle" | "planning" | "previewing" | "ready" | "manual_only";
  showSdkManualFallbackDialog: boolean;
  policyDraft: ProjectPolicy | null;
};

type ParsedDiffLine = {
  kind: "context" | "add" | "remove" | "meta";
  content: string;
  oldLineNumber: number | null;
  newLineNumber: number | null;
};

type ParsedDiffFile = {
  path: string;
  previousPath: string | null;
  additions: number;
  deletions: number;
  lines: ParsedDiffLine[];
};

function createSecretDraft(): SecretDraft {
  return {
    id: `secret-draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    label: "",
    value: "",
  };
}

function createRepoSecretMountDraft(secretRefId = "", mountAs = ""): RepoSecretMountDraft {
  return {
    id: `repo-secret-mount-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    secretRefId,
    mountAs,
  };
}

function normalizeDiffPath(rawPath: string | null | undefined): string | null {
  if (!rawPath || rawPath === "/dev/null") {
    return null;
  }
  if (rawPath.startsWith("a/") || rawPath.startsWith("b/")) {
    return rawPath.slice(2);
  }
  return rawPath;
}

function parseUnifiedDiff(diff: string | null | undefined): ParsedDiffFile[] {
  if (!diff?.trim()) {
    return [];
  }

  const files: ParsedDiffFile[] = [];
  let currentFile: ParsedDiffFile | null = null;
  let oldLineCursor: number | null = null;
  let newLineCursor: number | null = null;

  const pushCurrentFile = () => {
    if (currentFile) {
      files.push(currentFile);
    }
    currentFile = null;
    oldLineCursor = null;
    newLineCursor = null;
  };

  const ensureCurrentFile = () => {
    if (!currentFile) {
      currentFile = {
        path: "Patch preview",
        previousPath: null,
        additions: 0,
        deletions: 0,
        lines: [],
      };
    }
    return currentFile;
  };

  for (const line of diff.split("\n")) {
    if (line.startsWith("diff --git ")) {
      pushCurrentFile();
      const parts = line.split(" ");
      currentFile = {
        path: normalizeDiffPath(parts[3]) ?? normalizeDiffPath(parts[2]) ?? "Patch preview",
        previousPath: normalizeDiffPath(parts[2]),
        additions: 0,
        deletions: 0,
        lines: [],
      };
      continue;
    }

    if (line.startsWith("--- ")) {
      ensureCurrentFile().previousPath = normalizeDiffPath(line.slice(4).trim());
      continue;
    }

    if (line.startsWith("+++ ")) {
      ensureCurrentFile().path =
        normalizeDiffPath(line.slice(4).trim()) ?? ensureCurrentFile().path ?? "Patch preview";
      continue;
    }

    if (line.startsWith("@@")) {
      const file = ensureCurrentFile();
      const match = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      oldLineCursor = match ? Number(match[1]) : null;
      newLineCursor = match ? Number(match[2]) : null;
      file.lines.push({
        kind: "meta",
        content: line,
        oldLineNumber: null,
        newLineNumber: null,
      });
      continue;
    }

    const file = ensureCurrentFile();
    if (line.startsWith("+") && !line.startsWith("+++")) {
      file.additions += 1;
      file.lines.push({
        kind: "add",
        content: line,
        oldLineNumber: null,
        newLineNumber: newLineCursor,
      });
      newLineCursor = newLineCursor === null ? null : newLineCursor + 1;
      continue;
    }

    if (line.startsWith("-") && !line.startsWith("---")) {
      file.deletions += 1;
      file.lines.push({
        kind: "remove",
        content: line,
        oldLineNumber: oldLineCursor,
        newLineNumber: null,
      });
      oldLineCursor = oldLineCursor === null ? null : oldLineCursor + 1;
      continue;
    }

    file.lines.push({
      kind: "context",
      content: line,
      oldLineNumber: oldLineCursor,
      newLineNumber: newLineCursor,
    });
    oldLineCursor = oldLineCursor === null ? null : oldLineCursor + 1;
    newLineCursor = newLineCursor === null ? null : newLineCursor + 1;
  }

  pushCurrentFile();
  return files;
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

async function requestOnboardingState(projectId: string): Promise<ProjectOnboarding> {
  const requestKey = projectId.trim();
  if (!inFlightOnboardingRequests.has(requestKey)) {
    inFlightOnboardingRequests.set(
      requestKey,
      requestJson<ProjectOnboarding>(`projects/${encodeURIComponent(requestKey)}/onboarding`, {
        method: "GET",
      }).finally(() => {
        inFlightOnboardingRequests.delete(requestKey);
      }),
    );
  }
  return inFlightOnboardingRequests.get(requestKey)!;
}

function toProjectSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function humanizeRepositoryName(value: string): string {
  return value
    .split(/[-_]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function inferServiceTypeFromRepositoryName(
  value: string,
): "frontend" | "backend" | "fullstack" | "api" | "worker" | "cron" | "gateway" | "database" | "cache" | "other" {
  const normalized = value.toLowerCase();
  const hasFrontendSignal =
    normalized.includes("web") ||
    normalized.includes("frontend") ||
    normalized.includes("site") ||
    normalized.includes("client") ||
    normalized.includes("ui");
  const hasBackendSignal =
    normalized.includes("backend") || normalized.includes("server") || normalized.includes("fullstack");
  if (hasFrontendSignal && hasBackendSignal) {
    return "fullstack";
  }
  if (
    hasFrontendSignal
  ) {
    return "frontend";
  }
  if (normalized.includes("gateway") || normalized.includes("proxy")) {
    return "gateway";
  }
  if (normalized.includes("worker") || normalized.includes("queue")) {
    return "worker";
  }
  if (normalized.includes("cron") || normalized.includes("scheduler")) {
    return "cron";
  }
  if (normalized.includes("db") || normalized.includes("database") || normalized.includes("postgres")) {
    return "database";
  }
  if (normalized.includes("cache") || normalized.includes("redis")) {
    return "cache";
  }
  if (normalized.includes("api")) {
    return "api";
  }
  if (normalized.includes("backend") || normalized.includes("server")) {
    return "backend";
  }
  return "other";
}

export function ProjectOnboardingConsole() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const shellSession = useAppShellSession();
  const session = shellSession?.session ?? null;
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
  const [repoSecretMounts, setRepoSecretMounts] = useState<RepoSecretMountDraft[]>([]);
  const [serviceName, setServiceName] = useState("");
  const [serviceType, setServiceType] = useState<
    "frontend" | "backend" | "fullstack" | "api" | "worker" | "cron" | "gateway" | "database" | "cache" | "other"
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
  const [stepFivePreviewMode, setStepFivePreviewMode] = useState<"single" | "multi" | null>(null);
  const [showStepFiveAdvanced, setShowStepFiveAdvanced] = useState(false);
  const [repoProfileInference, setRepoProfileInference] = useState<RepoProfileInference | null>(null);
  const [repoProfileInferenceError, setRepoProfileInferenceError] = useState<string | null>(null);
  const [telemetryKeyName, setTelemetryKeyName] = useState("");
  const [telemetryKeyPlaintext, setTelemetryKeyPlaintext] = useState<string | null>(null);
  const [copiedTelemetryKey, setCopiedTelemetryKey] = useState(false);
  const [sdkEnvironment, setSdkEnvironment] = useState("production");
  const [sdkSetupMode, setSdkSetupMode] = useState<"automatic" | "manual">("automatic");
  const [sdkBootstrapPlan, setSdkBootstrapPlan] = useState<SdkBootstrapPlanPreview | null>(null);
  const [sdkBootstrapPreview, setSdkBootstrapPreview] = useState<SdkBootstrapPreview | null>(null);
  const [sdkLatestBootstrapPreview, setSdkLatestBootstrapPreview] = useState<SdkBootstrapPreview | null>(null);
  const [telemetryVerification, setTelemetryVerification] = useState<ProjectTelemetryVerification | null>(null);
  const [selectedSdkStrategyId, setSelectedSdkStrategyId] = useState("");
  const [dismissedSdkPreviewStrategyId, setDismissedSdkPreviewStrategyId] = useState<string | null>(null);
  const [sdkAutomaticRequested, setSdkAutomaticRequested] = useState(false);
  const [sdkAutomationStage, setSdkAutomationStage] = useState<
    "idle" | "planning" | "previewing" | "ready" | "manual_only"
  >("idle");
  const [showSdkManualFallbackDialog, setShowSdkManualFallbackDialog] = useState(false);
  const [policyDraft, setPolicyDraft] = useState<ProjectPolicy | null>(null);
  const [loadingRepoProfileInference, setLoadingRepoProfileInference] = useState(false);
  const [loadingSdkBootstrapPlan, setLoadingSdkBootstrapPlan] = useState(false);
  const [loadingSdkBootstrapPreview, setLoadingSdkBootstrapPreview] = useState(false);
  const [loadingTelemetryVerification, setLoadingTelemetryVerification] = useState(false);
  const [editingStepKey, setEditingStepKey] = useState<StepEditKey | null>(null);
  const [activeStep, setActiveStep] = useState<(typeof STEP_ORDER)[number]>("1");
  const stepRefs = useRef<Record<string, HTMLElement | null>>({});
  const editorSnapshotRef = useRef<OnboardingEditorSnapshot | null>(null);
  const repoProfileInferenceKeyRef = useRef("");
  const sdkBootstrapPlanKeyRef = useRef("");
  const sdkBootstrapPreviewKeyRef = useRef("");
  const telemetryVerificationKeyRef = useRef("");
  const sdkManualFallbackDialogKeyRef = useRef("");
  const singleRepoSecretMountSeedKeyRef = useRef("");

  const repositories = useMemo<ProviderRepository[]>(() => {
    if (!state) {
      return [];
    }
    return state.integrations.flatMap((integration) => integration.repositories);
  }, [state]);
  const dedupedIntegrations = useMemo(() => {
    if (!state) {
      return [];
    }
    const byKey = new Map<string, (typeof state.integrations)[number]>();
    for (const integration of state.integrations) {
      const accountKey = readIntegrationAccount(integration);
      const dedupeKey = [
        integration.integration.provider,
        accountKey.toLowerCase(),
        integration.integration.name.toLowerCase(),
      ].join(":");
      const existing = byKey.get(dedupeKey);
      if (!existing) {
        byKey.set(dedupeKey, integration);
        continue;
      }
      const currentRepoCount = integration.repositories.length;
      const existingRepoCount = existing.repositories.length;
      if (currentRepoCount > existingRepoCount) {
        byKey.set(dedupeKey, integration);
        continue;
      }
      if (
        currentRepoCount === existingRepoCount &&
        new Date(integration.integration.updated_at).getTime() >
          new Date(existing.integration.updated_at).getTime()
      ) {
        byKey.set(dedupeKey, integration);
      }
    }
    return Array.from(byKey.values());
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
  const sessionReady = createRequested ? true : Boolean(shellSession && !shellSession.sessionLoading);
  const [createMode, setCreateMode] = useState(createRequested);
  const [bootstrappingPage, setBootstrappingPage] = useState(!createRequested);
  const [initialContentReady, setInitialContentReady] = useState(createRequested);
  const currentProject = useMemo(
    () => session?.projects.find((project) => project.id === projectId) ?? session?.projects[0] ?? null,
    [projectId, session],
  );
  const onboardingState = state?.onboarding_state ?? null;
  const platformBaseUrl = state?.platform_base_url ?? "";
  const configuredRepositoryCount = useMemo(
    () => new Set((state?.repo_profiles ?? []).map((profile) => profile.provider_repository_id)).size,
    [state?.repo_profiles],
  );
  const detectedStepFiveMode = configuredRepositoryCount > 1 ? "multi" : "single";
  const effectiveStepFiveMode = stepFivePreviewMode ?? detectedStepFiveMode;
  const inferredSingleRepoProfile =
    effectiveStepFiveMode === "single" && (state?.repo_profiles.length ?? 0) === 1
      ? state?.repo_profiles[0] ?? null
      : null;
  const effectiveServiceRepoProfileId = selectedServiceRepoProfileId || inferredSingleRepoProfile?.id || "";
  const effectiveServiceRepoProfile =
    state?.repo_profiles.find((profile) => profile.id === effectiveServiceRepoProfileId) ?? null;
  const effectiveProjectService = useMemo(() => {
    if (!state?.project_services.length) {
      return null;
    }
    if (effectiveServiceRepoProfileId) {
      return (
        state.project_services.find((service) => service.repo_profile_id === effectiveServiceRepoProfileId) ?? null
      );
    }
    if (effectiveStepFiveMode === "single" && state.project_services.length === 1) {
      return state.project_services[0];
    }
    return null;
  }, [effectiveServiceRepoProfileId, effectiveStepFiveMode, state?.project_services]);
  const effectiveServiceRepository =
    repositories.find((repository) => repository.id === effectiveServiceRepoProfile?.provider_repository_id) ?? null;
  const inferredConnectedRepositoryId =
    onboardingState?.sdk_setup_provider_repository_id ??
    (repositories.length === 1 ? repositories[0]?.id ?? "" : "");
  const suggestedRepositoryId =
    effectiveServiceRepoProfile?.provider_repository_id ||
    selectedRepositoryId ||
    inferredConnectedRepositoryId;
  const effectiveSdkServiceName = effectiveProjectService?.name?.trim() || serviceName.trim() || "web-app";
  const sdkTargetRepositoryId = effectiveServiceRepository?.id ?? suggestedRepositoryId;
  const sdkPlanningBaseUrl = platformBaseUrl || "https://stimpact.example.com";
  const shouldLoadStepFiveData =
    activeStep === "5" || editingStepKey === "5" || Boolean(selectedRepositoryId) || Boolean(effectiveServiceRepoProfile);
  const shouldLoadStepSixData =
    activeStep === "6" ||
    editingStepKey === "6" ||
    Boolean(inferredConnectedRepositoryId) ||
    Boolean(selectedRepositoryId) ||
    Boolean(effectiveServiceRepoProfile);
  const shouldRunAutomaticSdkWorkflow =
    sdkSetupMode === "automatic" &&
    (sdkAutomaticRequested || onboardingState?.sdk_setup_status === "change_request");
  const shouldInspectSdkBootstrapPlan = shouldLoadStepSixData;
  const savedProfileSuggestionMatchesVerify =
    Boolean(effectiveServiceRepoProfile && repoProfileInference?.verify_command) &&
    (repoProfileInference?.verify_command ?? "") === verifyCommand;
  const savedProfileSuggestionMatchesInstall =
    Boolean(effectiveServiceRepoProfile && repoProfileInference?.install_command) &&
    (repoProfileInference?.install_command ?? "") === installCommand;
  const hasIncompleteRepoSecretMount =
    repoSecretMounts.some(
      (draft) =>
        (draft.secretRefId.trim().length > 0 || draft.mountAs.trim().length > 0) &&
        !(draft.secretRefId.trim().length > 0 && draft.mountAs.trim().length > 0),
    );
  const canAttachSecretToSingleFlow = !hasIncompleteRepoSecretMount;

  useEffect(() => {
    setCreateMode(createRequested);
    setBootstrappingPage(!createRequested);
    setInitialContentReady(createRequested);
  }, [createRequested]);

  const loadOnboardingState = useCallback(async (bootstrap = false, overrideProjectId?: string) => {
    const resolvedProjectId = (overrideProjectId ?? projectId).trim();
    if (!resolvedProjectId) {
      return;
    }
    const payload = bootstrap
      ? await requestJson<ProjectOnboarding>(
          `projects/${encodeURIComponent(resolvedProjectId)}/bootstrap`,
          {
            method: "POST",
          },
        )
      : await requestOnboardingState(resolvedProjectId);
    setState(payload);
    setSelectedRepositoryId((current) => {
      const repositoryIds = payload.integrations.flatMap((integration) =>
        integration.repositories.map((repository) => repository.id),
      );
      if (current && repositoryIds.includes(current)) {
        return current;
      }
      return payload.integrations[0]?.repositories[0]?.id ?? "";
    });
  }, [projectId]);

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
    if (createMode) {
      setInitialContentReady(true);
      setBootstrappingPage(false);
      return;
    }
    if (!shellSession || shellSession.sessionLoading) {
      setBootstrappingPage(true);
      return;
    }
    const preferredProject =
      shellSession.currentProject ??
      session?.projects.find((project) => project.id === shellSession.selectedProjectId) ??
      session?.projects[0] ??
      null;
    if (!projectId.trim() && preferredProject?.id) {
      setProjectId(preferredProject.id);
      return;
    }
    if (!projectId.trim()) {
      setInitialContentReady(true);
      setBootstrappingPage(false);
    }
  }, [createMode, projectId, session?.projects, shellSession]);

  useEffect(() => {
    if (!sessionReady) {
      return;
    }
    if (!projectId.trim()) {
      const awaitingPreferredProject =
        !createMode &&
        Boolean(
          shellSession?.currentProject ??
            session?.projects.find((project) => project.id === shellSession?.selectedProjectId) ??
            session?.projects[0],
        );
      if (awaitingPreferredProject) {
        setInitialContentReady(false);
        setBootstrappingPage(true);
        return;
      }
      setInitialContentReady(true);
      setBootstrappingPage(false);
      return;
    }
    setBootstrappingPage(true);
    setInitialContentReady(false);
    void loadOnboardingState(false)
      .catch((error) => {
        setErrorMessage(error instanceof Error ? error.message : "Unable to load onboarding.");
      })
      .finally(() => {
        setInitialContentReady(true);
        setBootstrappingPage(false);
      });
  }, [createMode, loadOnboardingState, projectId, sessionReady, session?.projects, shellSession]);

  useEffect(() => {
    if (effectiveStepFiveMode === "single" && inferredSingleRepoProfile && !selectedServiceRepoProfileId) {
      setSelectedServiceRepoProfileId(inferredSingleRepoProfile.id);
    }
  }, [effectiveStepFiveMode, inferredSingleRepoProfile, selectedServiceRepoProfileId]);

  useEffect(() => {
    if (!selectedRepositoryId && inferredConnectedRepositoryId) {
      setSelectedRepositoryId(inferredConnectedRepositoryId);
    }
  }, [inferredConnectedRepositoryId, selectedRepositoryId]);

  useEffect(() => {
    if (!effectiveServiceRepository) {
      return;
    }
    if (!serviceName.trim()) {
      setServiceName(humanizeRepositoryName(effectiveServiceRepository.name));
    }
    if (serviceType === "frontend") {
      setServiceType(inferServiceTypeFromRepositoryName(effectiveServiceRepository.name));
    }
  }, [effectiveServiceRepository, serviceName, serviceType]);

  useEffect(() => {
    if (!effectiveServiceRepoProfile) {
      return;
    }
    setRuntimeKind(effectiveServiceRepoProfile.runtime_kind);
    setBaseImage(effectiveServiceRepoProfile.base_image ?? "");
    setInstallCommand(effectiveServiceRepoProfile.install_command ?? "");
    setReproduceCommand(effectiveServiceRepoProfile.reproduce_command ?? "");
    setVerifyCommand(effectiveServiceRepoProfile.verify_command ?? "");
    setRepoSecretMounts(
      effectiveServiceRepoProfile.secret_mounts.map((mount) =>
        createRepoSecretMountDraft(mount.secret_ref.id, mount.mount_as),
      ),
    );
  }, [effectiveServiceRepoProfile]);

  useEffect(() => {
    if (!effectiveProjectService) {
      return;
    }
    setServiceName(effectiveProjectService.name);
    setServiceType(effectiveProjectService.service_type);
    setServiceOwner(effectiveProjectService.owner ?? "");
    setServiceDeployTarget(effectiveProjectService.deploy_target ?? "");
    setServiceRoutingNames(effectiveProjectService.routing_hints.service_names.join(", "));
    setServicePathPrefixes(effectiveProjectService.routing_hints.path_prefixes.join(", "));
    setServiceDomains(effectiveProjectService.routing_hints.domains.join(", "));
    setServiceTags(effectiveProjectService.routing_hints.tags.join(", "));
    setServiceHealthcheckCommand(effectiveProjectService.sandbox_healthcheck_command ?? "");
    setServiceHealthcheckUrl(effectiveProjectService.sandbox_healthcheck_url ?? "");
    setSelectedDependencyIds(
      effectiveProjectService.dependencies.map((dependency) => dependency.depends_on_service_id),
    );
  }, [effectiveProjectService]);

  useEffect(() => {
    if (!state) {
      return;
    }
    setPolicyDraft({
      ...state.policy,
      approved_services: [...state.policy.approved_services],
    });
  }, [state]);

  useEffect(() => {
    if (!telemetryKeyName.trim()) {
      setTelemetryKeyName(
        currentProject ? `${currentProject.name} telemetry key` : "Project telemetry key",
      );
    }
  }, [currentProject, telemetryKeyName]);

  useEffect(() => {
    setCopiedTelemetryKey(false);
  }, [telemetryKeyPlaintext]);

  useEffect(() => {
    setSdkSetupMode((current) => {
      if (onboardingState?.sdk_setup_status === "manual" || onboardingState?.sdk_setup_status === "deferred") {
        return "manual";
      }
      if (onboardingState?.sdk_setup_status === "change_request") {
        return "automatic";
      }
      return current;
    });
    if (onboardingState?.sdk_setup_status === "change_request") {
      setSdkAutomaticRequested(true);
    }
  }, [onboardingState?.sdk_setup_status, sdkBootstrapPlan, selectedSdkStrategyId]);

  useEffect(() => {
    if (!projectId.trim() || !sdkTargetRepositoryId || !effectiveSdkServiceName.trim()) {
      setSdkBootstrapPlan(null);
      setSdkBootstrapPreview(null);
      setSdkLatestBootstrapPreview(null);
      setSelectedSdkStrategyId("");
      setDismissedSdkPreviewStrategyId(null);
      setLoadingSdkBootstrapPlan(false);
      sdkBootstrapPlanKeyRef.current = "";
      sdkBootstrapPreviewKeyRef.current = "";
      return;
    }
    if (!shouldInspectSdkBootstrapPlan) {
      setLoadingSdkBootstrapPlan(false);
      return;
    }

    const requestKey = [
      projectId.trim(),
      sdkTargetRepositoryId,
      sdkPlanningBaseUrl,
      effectiveSdkServiceName.trim(),
      sdkEnvironment.trim() || "production",
    ].join("|");
    if (sdkBootstrapPlanKeyRef.current === requestKey && sdkBootstrapPlan) {
      setLoadingSdkBootstrapPlan(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setLoadingSdkBootstrapPlan(true);
    if (shouldRunAutomaticSdkWorkflow) {
      setSdkAutomationStage("planning");
    }
    void requestJson<SdkBootstrapPlanPreview>(
      `projects/${encodeURIComponent(projectId.trim())}/sdk-bootstrap/plan`,
      {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({
          project_id: projectId.trim(),
          provider_repository_id: sdkTargetRepositoryId,
          service_name: effectiveSdkServiceName.trim(),
          environment: sdkEnvironment.trim() || "production",
          base_url: sdkPlanningBaseUrl,
        }),
      },
    )
      .then((payload) => {
        if (cancelled) {
          return;
        }
        sdkBootstrapPlanKeyRef.current = requestKey;
        sdkBootstrapPreviewKeyRef.current = "";
        setSdkBootstrapPlan(payload);
        if (shouldRunAutomaticSdkWorkflow) {
          setSdkBootstrapPreview(null);
        }
        if (shouldRunAutomaticSdkWorkflow && !payload.strategies.some((item) => item.pr_supported)) {
          setSdkAutomationStage("manual_only");
          if (sdkManualFallbackDialogKeyRef.current !== requestKey) {
            sdkManualFallbackDialogKeyRef.current = requestKey;
            setShowSdkManualFallbackDialog(true);
          }
        }
        setSelectedSdkStrategyId((current) => {
          const preferredStrategyId =
            payload.strategies.find((item) => item.id === current)?.id ??
            payload.recommended_strategy_id ??
            payload.strategies[0]?.id ??
            "";
          return preferredStrategyId;
        });
        setDismissedSdkPreviewStrategyId((current) =>
          current && !payload.strategies.some((item) => item.id === current) ? null : current,
        );
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setSdkBootstrapPlan(null);
        if (shouldRunAutomaticSdkWorkflow) {
          setSdkBootstrapPreview(null);
        }
        setSdkLatestBootstrapPreview(null);
        setSelectedSdkStrategyId("");
        setDismissedSdkPreviewStrategyId(null);
        if (shouldRunAutomaticSdkWorkflow) {
          setSdkAutomationStage("idle");
        }
        setErrorMessage(error instanceof Error ? error.message : "Unable to inspect SDK bootstrap plan.");
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingSdkBootstrapPlan(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [
    projectId,
    sdkPlanningBaseUrl,
    shouldInspectSdkBootstrapPlan,
    shouldRunAutomaticSdkWorkflow,
    sdkBootstrapPlan,
    sdkEnvironment,
    effectiveSdkServiceName,
    sdkTargetRepositoryId,
  ]);

  useEffect(() => {
    const strategy =
      sdkBootstrapPlan?.strategies.find((item) => item.id === selectedSdkStrategyId) ??
      sdkBootstrapPlan?.strategies.find((item) => item.id === sdkBootstrapPlan.recommended_strategy_id) ??
      sdkBootstrapPlan?.strategies[0] ??
      null;
    if (
      !projectId.trim() ||
      !sdkTargetRepositoryId ||
      !platformBaseUrl ||
      !shouldRunAutomaticSdkWorkflow ||
      sdkSetupMode !== "automatic" ||
      !strategy ||
      dismissedSdkPreviewStrategyId === strategy.id
    ) {
      setLoadingSdkBootstrapPreview(false);
      return;
    }

    const requestKey = [
      projectId.trim(),
      sdkTargetRepositoryId,
      platformBaseUrl,
      effectiveSdkServiceName.trim(),
      sdkEnvironment.trim() || "production",
      strategy.id,
    ].join("|");
    if (sdkBootstrapPreviewKeyRef.current === requestKey && sdkBootstrapPreview?.selected_strategy_id === strategy.id) {
      setLoadingSdkBootstrapPreview(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setLoadingSdkBootstrapPreview(true);
    setSdkAutomationStage("previewing");
    void requestJson<SdkBootstrapPreview>(
      `projects/${encodeURIComponent(projectId.trim())}/sdk-bootstrap/preview`,
      {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({
          project_id: projectId.trim(),
          provider_repository_id: sdkTargetRepositoryId,
          service_name: effectiveSdkServiceName.trim(),
          environment: sdkEnvironment.trim() || "production",
          base_url: platformBaseUrl,
          strategy_id:
            strategy.pr_supported && !sdkBootstrapPlan?.requires_confirmation ? strategy.id : null,
        }),
      },
    )
      .then((payload) => {
        if (cancelled) {
          return;
        }
        sdkBootstrapPreviewKeyRef.current = requestKey;
        setSdkBootstrapPreview(payload);
        setSdkLatestBootstrapPreview(payload);
        setSdkAutomationStage("ready");
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setSdkBootstrapPreview(null);
        setSdkAutomationStage("idle");
        setErrorMessage(error instanceof Error ? error.message : "Unable to build SDK bootstrap preview.");
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingSdkBootstrapPreview(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [
    dismissedSdkPreviewStrategyId,
    platformBaseUrl,
    projectId,
    sdkBootstrapPlan,
    sdkBootstrapPreview?.selected_strategy_id,
    sdkEnvironment,
    sdkSetupMode,
    sdkTargetRepositoryId,
    selectedSdkStrategyId,
    effectiveSdkServiceName,
    shouldRunAutomaticSdkWorkflow,
  ]);

  const loadTelemetryVerification = useCallback(async () => {
    if (!projectId.trim() || !effectiveSdkServiceName.trim()) {
      setTelemetryVerification(null);
      setLoadingTelemetryVerification(false);
      telemetryVerificationKeyRef.current = "";
      return;
    }
    if (!shouldLoadStepSixData) {
      setLoadingTelemetryVerification(false);
      return;
    }
    const requestKey = [
      projectId.trim(),
      effectiveSdkServiceName.trim(),
      sdkEnvironment.trim() || "production",
    ].join("|");
    if (telemetryVerificationKeyRef.current === requestKey && telemetryVerification) {
      setLoadingTelemetryVerification(false);
      return;
    }
    setLoadingTelemetryVerification(true);
    try {
      const params = new URLSearchParams({
        service: effectiveSdkServiceName.trim(),
        environment: sdkEnvironment.trim() || "production",
      });
      const payload = await requestJson<ProjectTelemetryVerification>(
        `projects/${encodeURIComponent(projectId.trim())}/telemetry-verification?${params.toString()}`,
        { method: "GET" },
      );
      telemetryVerificationKeyRef.current = requestKey;
      setTelemetryVerification(payload);
    } catch (error) {
      setTelemetryVerification(null);
      setErrorMessage(error instanceof Error ? error.message : "Unable to load telemetry verification.");
    } finally {
      setLoadingTelemetryVerification(false);
    }
  }, [projectId, sdkEnvironment, effectiveSdkServiceName, shouldLoadStepSixData, telemetryVerification]);

  useEffect(() => {
    void loadTelemetryVerification();
  }, [loadTelemetryVerification, state?.telemetry_heartbeats]);

  useEffect(() => {
    if (!state) {
      return;
    }
    const availableSecretIds = new Set(state.secret_refs.map((secretRef) => secretRef.id));
    setRepoSecretMounts((current) =>
      current.filter((draft) => !draft.secretRefId || availableSecretIds.has(draft.secretRefId)),
    );
  }, [state]);

  useEffect(() => {
    if (effectiveStepFiveMode !== "single" || effectiveServiceRepoProfile || !state?.secret_refs.length) {
      return;
    }
    const seedKey = state.secret_refs.map((secretRef) => secretRef.id).join("|");
    if (!seedKey || singleRepoSecretMountSeedKeyRef.current === seedKey) {
      return;
    }
    setRepoSecretMounts((current) => {
      if (current.length) {
        return current;
      }
      singleRepoSecretMountSeedKeyRef.current = seedKey;
      return state.secret_refs.map((secretRef) =>
        createRepoSecretMountDraft(secretRef.id, secretRef.label),
      );
    });
  }, [effectiveServiceRepoProfile, effectiveStepFiveMode, state?.secret_refs]);

  useEffect(() => {
    if (!projectId.trim() || !suggestedRepositoryId) {
      setLoadingRepoProfileInference(false);
      setRepoProfileInference(null);
      setRepoProfileInferenceError(null);
      repoProfileInferenceKeyRef.current = "";
      return;
    }
    if (!shouldLoadStepFiveData) {
      setLoadingRepoProfileInference(false);
      return;
    }

    const requestKey = [projectId.trim(), suggestedRepositoryId].join("|");
    if (repoProfileInferenceKeyRef.current === requestKey) {
      setLoadingRepoProfileInference(false);
      setRepoProfileInferenceError(null);
      return;
    }

    let cancelled = false;
    const shouldClearStaleInference = repoProfileInferenceKeyRef.current !== requestKey;
    if (shouldClearStaleInference) {
      setRepoProfileInference(null);
    }
    setRepoProfileInferenceError(null);
    setLoadingRepoProfileInference(true);
    void requestJson<RepoProfileInference>(
      `projects/${encodeURIComponent(projectId.trim())}/provider-repositories/${encodeURIComponent(
        suggestedRepositoryId,
      )}/repo-profile-defaults`,
      { method: "GET" },
    )
      .then((inference) => {
        if (cancelled) {
          return;
        }
        repoProfileInferenceKeyRef.current = requestKey;
        setRepoProfileInference(inference);
        setRepoProfileInferenceError(null);
        if (!effectiveServiceRepoProfile) {
          setRuntimeKind(inference.runtime_kind);
          setBaseImage(inference.base_image ?? "");
          setInstallCommand(inference.install_command ?? "");
          setReproduceCommand(inference.reproduce_command ?? inference.verify_command ?? "");
          setVerifyCommand(inference.verify_command ?? "");
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        if (shouldClearStaleInference) {
          setRepoProfileInference(null);
        }
        setRepoProfileInferenceError(
          error instanceof Error ? error.message : "Unable to inspect the connected repo for default commands.",
        );
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingRepoProfileInference(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    effectiveServiceRepoProfile,
    projectId,
    shouldLoadStepFiveData,
    suggestedRepositoryId,
  ]);

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

  function captureEditorSnapshot(): OnboardingEditorSnapshot {
    return {
      selectedProvider,
      gitlabName,
      gitlabBaseUrl,
      lastGitLabAuthUrl,
      selectedRepositoryId,
      secretDrafts: secretDrafts.map((draft) => ({ ...draft })),
      runtimeKind,
      baseImage,
      installCommand,
      reproduceCommand,
      verifyCommand,
      networkAllowlist,
      repoSecretMounts: repoSecretMounts.map((mount) => ({ ...mount })),
      serviceName,
      serviceType,
      selectedServiceRepoProfileId,
      serviceOwner,
      serviceDeployTarget,
      serviceRoutingNames,
      servicePathPrefixes,
      serviceDomains,
      serviceTags,
      serviceHealthcheckCommand,
      serviceHealthcheckUrl,
      selectedDependencyIds: [...selectedDependencyIds],
      stepFivePreviewMode,
      showStepFiveAdvanced,
      telemetryKeyName,
      telemetryKeyPlaintext,
      sdkEnvironment,
      sdkSetupMode,
      sdkBootstrapPlan: sdkBootstrapPlan
        ? {
            ...sdkBootstrapPlan,
            warnings: [...sdkBootstrapPlan.warnings],
            strategies: sdkBootstrapPlan.strategies.map((strategy) => ({
              ...strategy,
              entrypoints: [...strategy.entrypoints],
              assumptions: [...strategy.assumptions],
              blockers: [...strategy.blockers],
              planned_files: strategy.planned_files.map((file) => ({ ...file })),
              env_vars: strategy.env_vars.map((envVar) => ({ ...envVar })),
              manual_steps: strategy.manual_steps.map((step) => ({ ...step })),
            })),
          }
        : null,
      sdkBootstrapPreview: sdkBootstrapPreview
        ? {
            ...sdkBootstrapPreview,
            strategy: {
              ...sdkBootstrapPreview.strategy,
              entrypoints: [...sdkBootstrapPreview.strategy.entrypoints],
              assumptions: [...sdkBootstrapPreview.strategy.assumptions],
              blockers: [...sdkBootstrapPreview.strategy.blockers],
              planned_files: sdkBootstrapPreview.strategy.planned_files.map((file) => ({ ...file })),
              env_vars: sdkBootstrapPreview.strategy.env_vars.map((envVar) => ({ ...envVar })),
              manual_steps: sdkBootstrapPreview.strategy.manual_steps.map((step) => ({ ...step })),
            },
            pull_request: { ...sdkBootstrapPreview.pull_request },
          }
        : null,
      selectedSdkStrategyId,
      dismissedSdkPreviewStrategyId,
      sdkAutomaticRequested,
      sdkAutomationStage,
      showSdkManualFallbackDialog,
      policyDraft: policyDraft ? { ...policyDraft, approved_services: [...policyDraft.approved_services] } : null,
      repoProfileInference: repoProfileInference
        ? {
            ...repoProfileInference,
            detected_from: [...repoProfileInference.detected_from],
            warnings: [...repoProfileInference.warnings],
          }
        : null,
      repoProfileInferenceError,
    };
  }

  function restoreEditorSnapshot(snapshot: OnboardingEditorSnapshot) {
    setSelectedProvider(snapshot.selectedProvider);
    setGitlabName(snapshot.gitlabName);
    setGitlabBaseUrl(snapshot.gitlabBaseUrl);
    setLastGitLabAuthUrl(snapshot.lastGitLabAuthUrl);
    setSelectedRepositoryId(snapshot.selectedRepositoryId);
    setSecretDrafts(snapshot.secretDrafts.map((draft) => ({ ...draft })));
    setRuntimeKind(snapshot.runtimeKind);
    setBaseImage(snapshot.baseImage);
    setInstallCommand(snapshot.installCommand);
    setReproduceCommand(snapshot.reproduceCommand);
    setVerifyCommand(snapshot.verifyCommand);
    setNetworkAllowlist(snapshot.networkAllowlist);
    setRepoSecretMounts(snapshot.repoSecretMounts.map((mount) => ({ ...mount })));
    setServiceName(snapshot.serviceName);
    setServiceType(snapshot.serviceType);
    setSelectedServiceRepoProfileId(snapshot.selectedServiceRepoProfileId);
    setServiceOwner(snapshot.serviceOwner);
    setServiceDeployTarget(snapshot.serviceDeployTarget);
    setServiceRoutingNames(snapshot.serviceRoutingNames);
    setServicePathPrefixes(snapshot.servicePathPrefixes);
    setServiceDomains(snapshot.serviceDomains);
    setServiceTags(snapshot.serviceTags);
    setServiceHealthcheckCommand(snapshot.serviceHealthcheckCommand);
    setServiceHealthcheckUrl(snapshot.serviceHealthcheckUrl);
    setSelectedDependencyIds([...snapshot.selectedDependencyIds]);
    setStepFivePreviewMode(snapshot.stepFivePreviewMode);
    setShowStepFiveAdvanced(snapshot.showStepFiveAdvanced);
    setTelemetryKeyName(snapshot.telemetryKeyName);
    setTelemetryKeyPlaintext(snapshot.telemetryKeyPlaintext);
    setSdkEnvironment(snapshot.sdkEnvironment);
    setSdkSetupMode(snapshot.sdkSetupMode);
    setSdkBootstrapPlan(
      snapshot.sdkBootstrapPlan
        ? {
            ...snapshot.sdkBootstrapPlan,
            warnings: [...snapshot.sdkBootstrapPlan.warnings],
            strategies: snapshot.sdkBootstrapPlan.strategies.map((strategy) => ({
              ...strategy,
              entrypoints: [...strategy.entrypoints],
              assumptions: [...strategy.assumptions],
              blockers: [...strategy.blockers],
              planned_files: strategy.planned_files.map((file) => ({ ...file })),
              env_vars: strategy.env_vars.map((envVar) => ({ ...envVar })),
              manual_steps: strategy.manual_steps.map((step) => ({ ...step })),
            })),
          }
        : null,
    );
    setSdkBootstrapPreview(
      snapshot.sdkBootstrapPreview
        ? {
            ...snapshot.sdkBootstrapPreview,
            strategy: {
              ...snapshot.sdkBootstrapPreview.strategy,
              entrypoints: [...snapshot.sdkBootstrapPreview.strategy.entrypoints],
              assumptions: [...snapshot.sdkBootstrapPreview.strategy.assumptions],
              blockers: [...snapshot.sdkBootstrapPreview.strategy.blockers],
              planned_files: snapshot.sdkBootstrapPreview.strategy.planned_files.map((file) => ({ ...file })),
              env_vars: snapshot.sdkBootstrapPreview.strategy.env_vars.map((envVar) => ({ ...envVar })),
              manual_steps: snapshot.sdkBootstrapPreview.strategy.manual_steps.map((step) => ({ ...step })),
            },
            pull_request: { ...snapshot.sdkBootstrapPreview.pull_request },
          }
        : null,
    );
    setSelectedSdkStrategyId(snapshot.selectedSdkStrategyId);
    setDismissedSdkPreviewStrategyId(snapshot.dismissedSdkPreviewStrategyId);
    setSdkAutomaticRequested(snapshot.sdkAutomaticRequested);
    setSdkAutomationStage(snapshot.sdkAutomationStage);
    setShowSdkManualFallbackDialog(snapshot.showSdkManualFallbackDialog);
    setPolicyDraft(
      snapshot.policyDraft
        ? { ...snapshot.policyDraft, approved_services: [...snapshot.policyDraft.approved_services] }
        : null,
    );
    setRepoProfileInference(
      snapshot.repoProfileInference
        ? {
            ...snapshot.repoProfileInference,
            detected_from: [...snapshot.repoProfileInference.detected_from],
            warnings: [...snapshot.repoProfileInference.warnings],
          }
        : null,
    );
    setRepoProfileInferenceError(snapshot.repoProfileInferenceError);
  }

  function beginStepEditing(stepKey: StepEditKey) {
    editorSnapshotRef.current = captureEditorSnapshot();
    setEditingStepKey(stepKey);
    setErrorMessage(null);
  }

  function cancelStepEditing() {
    if (editorSnapshotRef.current) {
      restoreEditorSnapshot(editorSnapshotRef.current);
    }
    editorSnapshotRef.current = null;
    setEditingStepKey(null);
    setErrorMessage(null);
  }

  function finishStepEditing() {
    editorSnapshotRef.current = null;
    setEditingStepKey(null);
  }

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
      finishStepEditing();
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
      finishStepEditing();
    }, "Provider repositories synced.");
  }

  function addSecretDraft() {
    setSecretDrafts((current) => [createSecretDraft(), ...current]);
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

  function normalizePendingSecretDrafts() {
    return secretDrafts
      .map((draft) => ({
        ...draft,
        label: draft.label.trim(),
        value: draft.value.trim(),
      }))
      .filter((draft) => draft.label || draft.value);
  }

  function attachRepoSecretMount(secretRefId: string) {
    const selectedSecret = state?.secret_refs.find((secretRef) => secretRef.id === secretRefId);
    if (!selectedSecret) {
      return;
    }
    setRepoSecretMounts((current) => {
      if (current.some((draft) => draft.secretRefId === secretRefId)) {
        return current;
      }
      return [...current, createRepoSecretMountDraft(secretRefId, selectedSecret.label)];
    });
  }

  function updateRepoSecretMount(
    draftId: string,
    field: "secretRefId" | "mountAs",
    nextValue: string,
  ) {
    setRepoSecretMounts((current) =>
      current.map((draft) => {
        if (draft.id !== draftId) {
          return draft;
        }
        if (field === "secretRefId") {
          const selectedSecret = state?.secret_refs.find((secretRef) => secretRef.id === nextValue);
          return {
            ...draft,
            secretRefId: nextValue,
            mountAs: draft.mountAs.trim() ? draft.mountAs : selectedSecret?.label ?? "",
          };
        }
        return { ...draft, mountAs: nextValue };
      }),
    );
  }

  function removeRepoSecretMount(draftId: string) {
    setRepoSecretMounts((current) => current.filter((draft) => draft.id !== draftId));
  }

  function buildRepoSecretMountPayload() {
    return repoSecretMounts
      .map((draft) => ({
        secret_ref_id: draft.secretRefId.trim(),
        mount_as: draft.mountAs.trim(),
      }))
      .filter((draft) => draft.secret_ref_id && draft.mount_as);
  }

  async function addSecrets() {
    const draftsToSave = normalizePendingSecretDrafts();
    if (!draftsToSave.length) {
      return;
    }
    await withFeedback(async () => {
      const createdSecrets = await Promise.all(
        draftsToSave.map((draft) =>
          requestJson<ProjectOnboarding["secret_refs"][number]>(
            `projects/${encodeURIComponent(projectId.trim())}/secret-refs`,
            {
              method: "POST",
              body: JSON.stringify({
                project_id: projectId.trim(),
                label: draft.label,
                value: draft.value,
              }),
            },
          ),
        ),
      );

      setState((current) =>
        current
          ? {
              ...current,
              secret_refs: [...current.secret_refs, ...createdSecrets],
              operational_readiness: {
                ...current.operational_readiness,
                has_secrets: true,
              },
            }
          : current,
      );
      setSecretDrafts([]);
      setOpenSecretMenuId(null);
      finishStepEditing();
    }, draftsToSave.length === 1 ? "Secret stored in AWS Secrets Manager." : "Secrets stored in AWS Secrets Manager.");
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
      finishStepEditing();
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
            reproduce_command: reproduceCommand || verifyCommand,
            verify_command: verifyCommand,
            success_criteria: "Sandbox verification exits successfully after the generated patch is applied.",
            network_allowlist: networkAllowlist
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            secret_mounts: buildRepoSecretMountPayload(),
          }),
        },
      );
      await loadOnboardingState(false);
      finishStepEditing();
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
            repo_profile_id: effectiveServiceRepoProfileId || null,
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
      resetServiceBuilder();
      if (!selectedServiceRepoProfileId && state?.repo_profiles[0]?.id) {
        setSelectedServiceRepoProfileId(state.repo_profiles[0].id);
      }
      await loadOnboardingState(false);
      finishStepEditing();
    }, "Project service configured.");
  }

  function resetServiceBuilder() {
    setServiceName("");
    setSelectedDependencyIds([]);
    setRepoSecretMounts([]);
    setServiceOwner("");
    setServiceDeployTarget("");
    setServiceRoutingNames("");
    setServicePathPrefixes("");
    setServiceDomains("");
    setServiceTags("");
    setServiceHealthcheckCommand("");
    setServiceHealthcheckUrl("");
    setShowStepFiveAdvanced(false);
  }

  async function completeSingleRepoSetup() {
    await withFeedback(async () => {
      let repoProfileId = effectiveServiceRepoProfileId;
      if (!repoProfileId) {
        const createdProfile = await requestJson<RepoProfile>(
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
              reproduce_command: reproduceCommand || verifyCommand,
              verify_command: verifyCommand,
              success_criteria: "Sandbox verification exits successfully after the generated patch is applied.",
              network_allowlist: networkAllowlist
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
              secret_mounts: buildRepoSecretMountPayload(),
            }),
          },
        );
        repoProfileId = createdProfile.id;
      }

      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/services`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            name: serviceName,
            slug: serviceSlug,
            service_type: serviceType,
            repo_profile_id: repoProfileId,
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
            dependencies: [],
          }),
        },
      );

      resetServiceBuilder();
      await loadOnboardingState(false);
      finishStepEditing();
    }, "Single-repo setup completed.");
  }

  async function createTelemetryApiKey() {
    await withFeedback(async () => {
      const created = sdkUsesBrowserCredential
        ? await requestJson<{ plaintext_key: string }>(
            `projects/${encodeURIComponent(projectId.trim())}/browser-keys`,
            {
              method: "POST",
              body: JSON.stringify({
                name: telemetryKeyName.trim() || "Browser telemetry key",
                allowed_origins: [],
              }),
            },
          )
        : await requestJson<ProjectApiKeyCreateResponse>(
            `projects/${encodeURIComponent(projectId.trim())}/api-keys`,
            {
              method: "POST",
              body: JSON.stringify({
                name: telemetryKeyName.trim() || "Project telemetry key",
              }),
            },
          );
      setTelemetryKeyPlaintext(created.plaintext_key);
      await loadOnboardingState(false);
    }, sdkUsesBrowserCredential ? "Telemetry browser key created." : "Telemetry API key created.");
  }

  async function copyTelemetryKeyToClipboard() {
    if (!telemetryKeyPlaintext) {
      return;
    }
    try {
      await navigator.clipboard.writeText(telemetryKeyPlaintext);
      setCopiedTelemetryKey(true);
      window.setTimeout(() => {
        setCopiedTelemetryKey(false);
      }, 1800);
    } catch {
      setErrorMessage(`Unable to copy the ${sdkCredentialLabel} to your clipboard.`);
    }
  }

  async function saveSdkSetupStatus(
    status: "manual" | "deferred" | "change_request",
    options?: { changeRequestUrl?: string | null },
  ) {
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/onboarding-state`,
        {
          method: "PUT",
          body: JSON.stringify({
            sdk_setup_status: status,
            sdk_setup_provider_repository_id: sdkTargetRepositoryId || null,
            sdk_setup_change_request_url: options?.changeRequestUrl ?? null,
          }),
        },
      );
      await loadOnboardingState(false);
      finishStepEditing();
    }, "SDK onboarding preference saved.");
  }

  async function createSdkBootstrapChangeRequest() {
    if (!sdkTargetRepositoryId) {
      setErrorMessage("Choose and configure a repository before generating an SDK bootstrap PR.");
      return;
    }
    if (!selectedSdkStrategy) {
      setErrorMessage("Preview the detected SDK bootstrap plan before generating a PR.");
      return;
    }
    if (!selectedSdkStrategy.pr_supported) {
      setErrorMessage("The selected SDK strategy requires manual setup instead of an automated PR.");
      return;
    }
    if (!sdkBootstrapPreview) {
      setErrorMessage("Wait for the SDK bootstrap preview to finish before approving PR creation.");
      return;
    }
    if (!sdkBootstrapPreview.attempt.change_request_allowed) {
      setErrorMessage(
        sdkBootstrapPreview.attempt.failure_reason ??
          "This SDK patch still needs manual review before a PR can be created.",
      );
      return;
    }
    if (!platformBaseUrl) {
      setErrorMessage("A public Stimpact platform URL is required before generating an SDK bootstrap PR.");
      return;
    }
    await withFeedback(async () => {
      const response = await requestJson<SdkBootstrapChangeRequestResponse>(
        `projects/${encodeURIComponent(projectId.trim())}/sdk-bootstrap/change-request`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId.trim(),
            provider_repository_id: sdkTargetRepositoryId,
            api_key_name: telemetryKeyName.trim() || "Project telemetry key",
            service_name: effectiveSdkServiceName.trim(),
            environment: sdkEnvironment.trim() || "production",
            base_url: platformBaseUrl,
            strategy_id: sdkBootstrapPreview.selected_strategy_id,
            branch_name: sdkBootstrapPreview.pull_request.branch_name,
          }),
        },
      );
      setTelemetryKeyPlaintext(response.plaintext_key);
      setSdkBootstrapPreview(null);
      await loadOnboardingState(false);
      finishStepEditing();
    }, "SDK bootstrap PR opened.");
  }

  function dismissSdkBootstrapPreview() {
    sdkManualFallbackDialogKeyRef.current = "";
    setSdkSetupMode("manual");
    setSdkAutomaticRequested(false);
    setSdkAutomationStage("idle");
    setDismissedSdkPreviewStrategyId(selectedSdkStrategy?.id ?? null);
    setShowSdkManualFallbackDialog(false);
  }

  function startAutomaticSdkWorkflow() {
    sdkManualFallbackDialogKeyRef.current = "";
    setSdkSetupMode("automatic");
    if (!sdkTargetRepositoryId || !platformBaseUrl || !projectId.trim() || !effectiveSdkServiceName.trim()) {
      setSdkAutomaticRequested(false);
      setSdkAutomationStage("idle");
      setShowSdkManualFallbackDialog(false);
      setErrorMessage(null);
      return;
    }
    setSdkAutomaticRequested(true);
    setDismissedSdkPreviewStrategyId(null);
    setSdkBootstrapPreview(null);
    setSdkLatestBootstrapPreview(null);
    setSdkAutomationStage("planning");
    setShowSdkManualFallbackDialog(false);
    setErrorMessage(null);
  }

  function chooseAutomaticSdkMode() {
    setSdkSetupMode("automatic");
    setSdkAutomaticRequested(false);
    setSdkAutomationStage("idle");
    setSdkBootstrapPreview(null);
    setSdkLatestBootstrapPreview(null);
    setShowSdkManualFallbackDialog(false);
    setErrorMessage(null);
  }

  function openManualSdkMode() {
    sdkManualFallbackDialogKeyRef.current = "";
    setSdkSetupMode("manual");
    setSdkAutomaticRequested(false);
    setSdkAutomationStage("idle");
    setShowSdkManualFallbackDialog(false);
    setErrorMessage(null);
  }

  async function saveAutomationControls() {
    if (!policyDraft) {
      return;
    }
    await withFeedback(async () => {
      await requestJson(
        `projects/${encodeURIComponent(projectId.trim())}/policy`,
        {
          method: "PUT",
          body: JSON.stringify({
            autonomy_mode: policyDraft.autonomy_mode,
            require_human_approval: policyDraft.require_human_approval,
            allow_production_writes: policyDraft.allow_production_writes,
            allow_low_risk_autonomy: policyDraft.allow_low_risk_autonomy,
            block_during_active_deploys: policyDraft.block_during_active_deploys,
            restrict_to_approved_services: policyDraft.restrict_to_approved_services,
            require_rollback_plan: policyDraft.require_rollback_plan,
            require_post_action_verification: policyDraft.require_post_action_verification,
            approved_services: policyDraft.approved_services,
            failure_classifier_enabled: policyDraft.failure_classifier_enabled,
            root_cause_enabled: policyDraft.root_cause_enabled,
            patch_planner_enabled: policyDraft.patch_planner_enabled,
            runbook_executor_enabled: policyDraft.runbook_executor_enabled,
          }),
        },
      );
      await loadOnboardingState(false);
      finishStepEditing();
    }, "Automation controls saved.");
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
      await fetch("/api/projects/current", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ project_id: payload.id }),
      });
      await shellSession?.refreshSession();
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
  const hasActiveApiKeys = state?.operational_readiness.has_active_api_keys ?? false;
  const hasActiveBrowserKeys = state?.operational_readiness.has_active_browser_keys ?? false;
  const hasReviewedPolicy = state?.operational_readiness.policy_reviewed ?? false;
  const hasSdkSetup = state?.operational_readiness.sdk_setup_ready ?? false;
  const activeApiKeys = state?.api_keys.filter((item) => item.status === "active") ?? [];
  const activeBrowserKeys = state?.browser_keys.filter((item) => item.status === "active") ?? [];
  const hasAnyActiveTelemetryKeys = hasActiveApiKeys || hasActiveBrowserKeys;
  const sdkStatusLabel =
    onboardingState?.sdk_setup_status === "change_request"
      ? "Bootstrap PR opened"
      : onboardingState?.sdk_setup_status === "manual"
        ? "Manual setup confirmed"
        : onboardingState?.sdk_setup_status === "deferred"
          ? "Deferred"
          : "Pending";
  const telemetryVerificationStatusLabel =
    telemetryVerification?.status === "healthy"
      ? "Live heartbeat detected"
      : telemetryVerification?.status === "stale"
        ? "Heartbeat stale"
        : loadingTelemetryVerification
          ? "Checking heartbeat"
          : "Waiting for first heartbeat";
  const sdkRepositoryLabel = sdkTargetRepositoryId
    ? (() => {
        const repository = repositories.find((candidate) => candidate.id === sdkTargetRepositoryId);
        return repository ? `${repository.owner}/${repository.name}` : sdkTargetRepositoryId;
      })()
    : "Choose and configure a repository first";
  const sdkPlannerRuntimeLabel = sdkBootstrapPlan?.runtime ?? "Waiting for repository signal";
  const selectedSdkStrategy =
    sdkBootstrapPlan?.strategies.find((item) => item.id === selectedSdkStrategyId) ??
    sdkBootstrapPlan?.strategies.find((item) => item.id === sdkBootstrapPlan.recommended_strategy_id) ??
    sdkBootstrapPlan?.strategies[0] ??
    null;
  const sdkPreviewAttempts =
    sdkBootstrapPreview?.attempts ??
    sdkLatestBootstrapPreview?.attempts ??
    (sdkBootstrapPreview?.attempt ? [sdkBootstrapPreview.attempt] : sdkLatestBootstrapPreview?.attempt ? [sdkLatestBootstrapPreview.attempt] : []);
  const sdkPatchAttempt = sdkBootstrapPreview?.attempt ?? sdkLatestBootstrapPreview?.attempt ?? null;
  const automaticSdkAvailable = Boolean(selectedSdkStrategy?.pr_supported);
  const sdkAutomationStageLabel =
    sdkAutomationStage === "planning"
      ? "Thinking"
      : sdkAutomationStage === "previewing"
        ? "Drafting preview"
        : sdkAutomationStage === "ready"
          ? sdkPatchAttempt?.verification.status === "failed"
            ? "Verification blocked"
            : sdkPatchAttempt?.verification.status === "needs_review"
              ? "Ready with review notes"
              : "Ready for review"
          : sdkAutomationStage === "manual_only"
            ? "Manual only"
            : "Idle";
  const automaticWorkflowItems = [
    {
      id: "inspect",
      label: "Inspect repository",
      detail: "Read manifests, entrypoints, and runtime structure.",
      state:
        sdkAutomationStage === "planning" ||
        sdkAutomationStage === "previewing" ||
        sdkAutomationStage === "ready" ||
        sdkAutomationStage === "manual_only"
          ? "complete"
          : sdkSetupMode === "automatic" && sdkAutomaticRequested
            ? "active"
            : "pending",
    },
    {
      id: "decide",
      label: "Choose integration path",
      detail: "Rank deterministic and model-assisted candidates, then keep trying until one is reviewable.",
      state:
        sdkAutomationStage === "previewing" ||
        sdkAutomationStage === "ready" ||
        sdkAutomationStage === "manual_only"
          ? "complete"
          : sdkAutomationStage === "planning"
            ? "active"
            : "pending",
    },
    {
      id: "draft",
      label: "Draft patch",
      detail: "Generate the exact diff from the selected runtime surface.",
      state:
        sdkPatchAttempt?.patch_generated
          ? "complete"
          : sdkAutomationStage === "previewing"
            ? "active"
            : sdkAutomationStage === "manual_only"
              ? "blocked"
              : "pending",
    },
    {
      id: "apply",
      label: "Apply patch",
      detail: "Replay the change in a temp checkout to prove it applies cleanly.",
      state:
        sdkPatchAttempt?.patch_applied
          ? "complete"
          : sdkPatchAttempt?.failure_stage === "apply"
            ? "blocked"
            : sdkAutomationStage === "previewing" && sdkPatchAttempt?.patch_generated
              ? "active"
              : "pending",
    },
    {
      id: "verify",
      label: "Verify patch",
      detail: "Run a focused verification check before allowing PR creation.",
      state:
        sdkPatchAttempt?.verification.status === "passed" || sdkPatchAttempt?.verification.status === "needs_review"
          ? "complete"
          : sdkPatchAttempt?.verification.status === "failed"
            ? "blocked"
            : sdkAutomationStage === "previewing" && sdkPatchAttempt?.patch_applied
              ? "active"
              : "pending",
    },
  ] as const;
  const sdkCompletedWorkflowCount = automaticWorkflowItems.filter((item) => item.state === "complete").length;
  const sdkVisibleWorkflowItems = automaticWorkflowItems.filter((item) => item.state !== "pending");
  const sdkActiveWorkflowIndex = automaticWorkflowItems.findIndex((item) => item.state === "active");
  const sdkBlockedWorkflowIndex = automaticWorkflowItems.findIndex((item) => item.state === "blocked");
  const sdkWorkflowProgressUnits =
    sdkCompletedWorkflowCount +
    (sdkActiveWorkflowIndex !== -1 ? 0.65 : sdkBlockedWorkflowIndex !== -1 ? 0.65 : 0);
  const sdkWorkflowProgressPercent = automaticWorkflowItems.length
    ? Math.max(0, Math.min(100, (sdkWorkflowProgressUnits / automaticWorkflowItems.length) * 100))
    : 0;
  const sdkWorkflowProgressTone =
    sdkActiveWorkflowIndex !== -1
      ? "active"
      : sdkBlockedWorkflowIndex !== -1
        ? "blocked"
        : sdkCompletedWorkflowCount === automaticWorkflowItems.length
          ? "complete"
          : "idle";
  const sdkAutomationSummaryItems = [
    { label: "Target service", value: effectiveSdkServiceName },
    { label: "Target repository", value: sdkRepositoryLabel },
    { label: "Planner runtime", value: sdkPlannerRuntimeLabel },
  ] as const;
  const sdkEntryPointLabel = selectedSdkStrategy?.entrypoints[0] ?? "the detected runtime entrypoint";
  const sdkSelectedStrategyBlockers = selectedSdkStrategy?.blockers ?? [];
  const sdkAttemptWarnings = sdkPatchAttempt?.warnings ?? [];
  const sdkRequiresConfirmationMessage = sdkBootstrapPlan?.requires_confirmation
    ? "Multiple plausible SDK surfaces were detected. Review the selected strategy before creating the PR so the agent patches the right runtime entrypoint."
    : null;
  const sdkStrategyConfidenceLabel = selectedSdkStrategy ? `${selectedSdkStrategy.confidence} confidence` : "Waiting for strategy";
  const sdkManualBlockers = selectedSdkStrategy?.blockers ?? [];
  const sdkAgentFeedItems = [
    {
      id: "requested",
      thought: sdkAutomaticRequested
        ? `Automatic attempt started for ${effectiveSdkServiceName}.`
        : "Waiting for you to start the automatic attempt.",
      state: sdkAutomaticRequested ? "complete" : "pending",
    },
    {
      id: "inspected",
      thought: sdkBootstrapPlan
        ? `Repository inspection finished for ${sdkRepositoryLabel}.`
        : "Inspecting repository manifests, entrypoints, and runtime signals.",
      state:
        sdkBootstrapPlan || sdkAutomationStage === "previewing" || sdkAutomationStage === "ready" || sdkAutomationStage === "manual_only"
          ? "complete"
          : sdkAutomationStage === "planning"
            ? "active"
            : "pending",
    },
    {
      id: "strategy",
      thought: selectedSdkStrategy
        ? `Selected ${selectedSdkStrategy.framework} at ${sdkEntryPointLabel}.`
        : sdkAutomationStage === "manual_only"
          ? "No safe automatic integration strategy was confirmed for this repository."
          : "Choosing the safest SDK integration strategy from the inspection results.",
      state:
        sdkAutomationStage === "manual_only"
          ? "blocked"
          : selectedSdkStrategy && sdkBootstrapPlan
            ? "complete"
            : sdkBootstrapPlan
              ? "active"
              : "pending",
    },
    {
      id: "preview",
      thought:
        sdkPatchAttempt?.verification.status === "passed"
          ? `Prepared review-ready PR preview on ${sdkBootstrapPreview?.pull_request.branch_name ?? "the proposed branch"}.`
          : sdkPatchAttempt?.verification.status === "needs_review"
            ? "Prepared a preview, but this patch still needs human review before PR creation."
            : sdkPatchAttempt?.verification.status === "failed"
              ? "Generated a preview, but verification failed before PR creation could be approved."
              : sdkAutomationStage === "manual_only"
                ? "Automatic preview stopped because this repository needs manual setup."
                : "Generating the exact patch diff and PR metadata for review.",
      state:
        sdkPatchAttempt?.verification.status === "failed"
          ? "blocked"
          : sdkAutomationStage === "manual_only"
            ? "blocked"
            : sdkBootstrapPreview || sdkAutomationStage === "ready"
              ? "complete"
              : sdkAutomationStage === "previewing"
                ? "active"
                : "pending",
    },
  ] as const;
  const sdkVisibleAgentFeedItems = sdkAgentFeedItems.filter(
    (item, index) => item.state !== "pending" || (!sdkAutomaticRequested && index === 0),
  );
  const sdkAutomaticRunStarted =
    sdkAutomaticRequested ||
    loadingSdkBootstrapPlan ||
    loadingSdkBootstrapPreview ||
    sdkAutomationStage !== "idle" ||
    Boolean(sdkBootstrapPreview) ||
    onboardingState?.sdk_setup_status === "change_request";
  const sdkActiveThought =
    sdkAgentFeedItems.find((item) => item.state === "active")?.thought ??
    sdkAgentFeedItems.find((item) => item.state === "blocked")?.thought ??
    sdkAgentFeedItems.findLast((item) => item.state === "complete")?.thought ??
    sdkAgentFeedItems[0]?.thought ??
    "";
  const selectedManualFallbackStrategy =
    sdkBootstrapPlan?.strategies.find((item) => item.id === selectedSdkStrategyId) ??
    sdkBootstrapPlan?.strategies[0] ??
    null;
  const sdkUsesBrowserCredential =
    selectedSdkStrategy?.env_vars.some((item) => item.name.includes("BROWSER_KEY")) ?? false;
  const sdkCredentialEnvVarName =
    selectedSdkStrategy?.env_vars.find(
      (item) => item.name.includes("BROWSER_KEY") || item.name.includes("API_KEY"),
    )?.name ?? (sdkUsesBrowserCredential ? "STIMPACT_BROWSER_KEY" : "STIMPACT_API_KEY");
  const sdkCredentialPlaceholder = sdkUsesBrowserCredential
    ? "stimp_browser_replace_me"
    : "stimp_live_replace_me";
  const sdkCredentialLabel = sdkUsesBrowserCredential ? "browser key" : "API key";
  const sdkEnvironmentSnippet = selectedSdkStrategy
    ? selectedSdkStrategy.env_vars
        .map((item) => {
          const exampleValue =
            item.name.includes("BASE_URL")
              ? platformBaseUrl || item.example_value
              : item.name.includes("PROJECT_ID")
                ? projectId || item.example_value
                : item.name.includes("API_KEY") || item.name.includes("BROWSER_KEY")
                  ? telemetryKeyPlaintext || sdkCredentialPlaceholder
                  : item.name.includes("SERVICE")
                    ? effectiveSdkServiceName
                    : item.name.includes("ENVIRONMENT")
                      ? sdkEnvironment || "production"
                      : item.example_value;
          return `${item.name}=${exampleValue}`;
        })
        .join("\n")
    : "";
  const sdkAutomaticFailureExplanation =
    sdkPatchAttempt?.failure_reason ??
    sdkPatchAttempt?.verification.summary ??
    sdkAttemptWarnings[0] ??
    null;
  const sdkPreviewDiffFiles = useMemo(
    () => parseUnifiedDiff(sdkBootstrapPreview?.patch_diff),
    [sdkBootstrapPreview?.patch_diff],
  );
  const sdkPreviewEnvVarNames = sdkBootstrapPreview?.strategy.env_vars.map((item) => item.name) ?? [];
  const sdkPreviewEnvVarSummary = sdkPreviewEnvVarNames.length
    ? sdkPreviewEnvVarNames.join(", ")
    : "the required Stimpact runtime variables";
  const sdkPreviewNextSteps = sdkBootstrapPreview
    ? [
        {
          title: sdkBootstrapPreview.attempt.change_request_allowed
            ? "Approve and create the PR"
            : "Review the preview before opening a PR",
          detail: sdkBootstrapPreview.attempt.change_request_allowed
            ? `If the diff looks right, open the PR from this screen. Stimpact will generate the required ${sdkCredentialLabel} during PR creation.`
            : sdkBootstrapPreview.attempt.verification.summary ??
              "This preview still needs human review before the PR should be created.",
        },
        {
          title: `Add the Stimpact ${sdkCredentialLabel} and env vars`,
          detail: telemetryKeyPlaintext
            ? `Add ${sdkPreviewEnvVarSummary} to your deployment provider. Use ${sdkCredentialEnvVarName}=${telemetryKeyPlaintext} for the runtime credential value.`
            : `After creating the PR, add ${sdkPreviewEnvVarSummary} to your deployment provider. Stimpact will generate the ${sdkCredentialEnvVarName} when the PR is opened.`,
        },
        {
          title: "Merge, redeploy, then refresh heartbeat verification",
          detail: `After the patch lands, redeploy ${effectiveSdkServiceName} in ${sdkEnvironment.trim() || "production"} and return here to verify the first heartbeat.`,
        },
      ]
    : [];
  const sdkAttemptHistorySummary =
    sdkPreviewAttempts.length > 1
      ? `Tried ${sdkPreviewAttempts.length} candidate surfaces before selecting the best available result.`
      : sdkPreviewAttempts.length === 1
        ? "Tried 1 candidate surface."
        : null;
  const sdkCodeSnippet = (selectedSdkStrategy?.preview_snippet ?? "")
    .replaceAll("<public-stimpact-url>", platformBaseUrl || "<public-stimpact-url>")
    .replaceAll("<project-id>", projectId || "<project-id>");
  const sdkManualActionItems = [
    {
      title: "Install the SDK dependency",
      detail: "Run this in the detected app before making any code changes.",
      code: selectedSdkStrategy?.install_command ?? "# Install the SDK with your package manager",
    },
    {
      title: "Add the required environment variables",
      detail: "Set these values in your local and deployed environment configuration.",
      code: sdkEnvironmentSnippet || "# No environment variables detected",
    },
    {
      title: `Wire the SDK into ${sdkEntryPointLabel}`,
      detail: "Use this starter snippet in the app entrypoint the planner identified for this service.",
      code: sdkCodeSnippet || "# No starter snippet available",
    },
    {
      title: "Verify the first heartbeat",
      detail: "Deploy or run the updated service, trigger the app once, then come back here and confirm telemetry is arriving for this exact service and environment.",
      code: `Service: ${effectiveSdkServiceName}\nEnvironment: ${sdkEnvironment || "production"}`,
    },
  ] as const;
  const sdkManualPrimarySteps = sdkManualActionItems.slice(0, 3);
  const sdkManualFollowUpItems = [
    telemetryKeyPlaintext
      ? `Add ${sdkCredentialEnvVarName}=${telemetryKeyPlaintext} and the required Stimpact env vars to your deployed environment.`
      : `Add ${sdkCredentialEnvVarName} and the required Stimpact env vars to your deployed environment before redeploying.`,
    !platformBaseUrl
      ? "Replace the placeholder Stimpact base URL with your real public platform URL before deploying."
      : `Confirm the Stimpact base URL points at ${platformBaseUrl}.`,
    `Redeploy ${effectiveSdkServiceName} in ${sdkEnvironment.trim() || "production"}.`,
    "Return here and refresh heartbeat verification to confirm the SDK is live.",
  ];
  const sdkManualExtraNotes = [
    ...(sdkAutomaticFailureExplanation ? [sdkAutomaticFailureExplanation] : []),
    ...((selectedSdkStrategy?.manual_steps.map((item) => item.content) ?? []) as string[]),
    ...sdkManualBlockers,
  ];
  const canCompleteSingleRepoSetup =
    Boolean(serviceName.trim()) &&
    Boolean(serviceSlug.trim()) &&
    Boolean(verifyCommand.trim()) &&
    Boolean(effectiveServiceRepoProfileId || selectedRepositoryId) &&
    canAttachSecretToSingleFlow;
  const pendingSecretDrafts = normalizePendingSecretDrafts();
  const canSaveSecretDrafts =
    pendingSecretDrafts.length > 0 &&
    pendingSecretDrafts.every((draft) => Boolean(draft.label) && Boolean(draft.value));

  if (!createMode && (!sessionReady || !initialContentReady || bootstrappingPage)) {
    return (
      <div className="flex min-h-[calc(100vh-7rem)] items-center justify-center px-6 lg:min-h-[calc(100vh-9.5rem)]">
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
          <p className="landing-static-tag mx-auto block w-fit !text-center">
            Project onboarding
          </p>
          <h1 className="mx-auto mt-4 max-w-4xl text-4xl font-semibold tracking-tight text-[#171717] lg:text-[3.35rem]">
            Set up your project in one guided flow
          </h1>

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
              {
                step: "6",
                label: "Telemetry",
                detail: "Create telemetry credentials and SDK path",
                complete: hasAnyActiveTelemetryKeys && hasSdkSetup,
              },
              {
                step: "7",
                label: "Controls",
                detail: "Review automation policy",
                complete: hasReviewedPolicy,
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
          editable={false}
          isEditing={false}
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
          editable={hasIntegrations}
          isEditing={editingStepKey === "2"}
          editDisabled={Boolean(editingStepKey) && editingStepKey !== "2"}
          onEdit={() => beginStepEditing("2")}
          onCancelEdit={cancelStepEditing}
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
          editable={hasRepositories}
          isEditing={editingStepKey === "3"}
          editDisabled={Boolean(editingStepKey) && editingStepKey !== "3"}
          onEdit={() => beginStepEditing("3")}
          onCancelEdit={cancelStepEditing}
          sectionRef={(node) => {
            stepRefs.current["3"] = node;
          }}
        >
          <div className="space-y-4">
            {dedupedIntegrations.length ? (
              dedupedIntegrations.map((integration) => (
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
                    {editingStepKey === "3" ? (
                      <ActionButton
                        label="Sync latest repos"
                        onClick={() => syncRepositories(integration.integration.id)}
                        disabled={loading}
                        variant="secondary"
                      />
                    ) : null}
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
            {editingStepKey === "3" ? (
              <div className="flex flex-wrap gap-3">
                <ActionButton
                  label="Save repository selection"
                  onClick={finishStepEditing}
                  disabled={loading || !selectedRepositoryId}
                  variant="success"
                />
              </div>
            ) : null}
          </div>
        </StepPanel>

        <StepPanel
          step="04"
          stepKey="4"
          title="Add runtime secrets"
          description="Store runtime secrets in AWS Secrets Manager and keep only metadata in the platform database."
          complete={hasSecrets}
          editable={hasSecrets}
          isEditing={editingStepKey === "4"}
          editDisabled={Boolean(editingStepKey) && editingStepKey !== "4"}
          onEdit={() => beginStepEditing("4")}
          onCancelEdit={cancelStepEditing}
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
                          type="text"
                          placeholder="Paste the secret value"
                          name={`secret-value-${draft.id}`}
                          suppressPasswordManagers
                        />
                      </div>
                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        <ActionButton
                          label={secretDrafts.length > 1 || state?.secret_refs.length ? "Remove row" : "Clear row"}
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
            {secretDrafts.length ? (
              <div className="flex flex-wrap gap-3">
                <ActionButton
                  label={pendingSecretDrafts.length > 1 ? "Save secrets" : "Save secret"}
                  onClick={() => {
                    void addSecrets();
                  }}
                  disabled={loading || !canSaveSecretDrafts}
                  variant="success"
                />
                <ActionButton
                  label="Cancel edits"
                  onClick={() => {
                    if (editingStepKey === "4") {
                      cancelStepEditing();
                      return;
                    }
                    setSecretDrafts(state?.secret_refs.length ? [] : [createSecretDraft()]);
                  }}
                  disabled={loading}
                  variant="secondary"
                />
              </div>
            ) : null}
          </div>
        </StepPanel>

        <StepPanel
          step="05"
          stepKey="5"
          title="Create repo profiles and map services"
          description="Define sandbox commands, then turn those repo profiles into named project services with routing hints and dependencies."
          complete={hasRepoProfiles && hasProjectServices}
          editable={hasRepoProfiles || hasProjectServices}
          isEditing={editingStepKey === "5"}
          editDisabled={Boolean(editingStepKey) && editingStepKey !== "5"}
          onEdit={() => beginStepEditing("5")}
          onCancelEdit={cancelStepEditing}
          sectionRef={(node) => {
            stepRefs.current["5"] = node;
          }}
        >
          <div className="rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.72)] p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="space-y-1">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8a8178]">
                  Step 5 mode
                </p>
                <p className="text-sm leading-6 text-[#64584f]">
                  Auto-detected as{" "}
                  <span className="font-semibold text-[#171717]">
                    {detectedStepFiveMode === "single" ? "single repo" : "multi repo"}
                  </span>{" "}
                  based on the repo profiles already configured for this project.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {[
                  { value: null, label: "Auto" },
                  { value: "single" as const, label: "Single repo" },
                  { value: "multi" as const, label: "Multi repo" },
                ].map((option) => {
                  const active =
                    stepFivePreviewMode === option.value ||
                    (option.value === null && stepFivePreviewMode === null);
                  return (
                    <button
                      key={option.label}
                      type="button"
                      onClick={() => setStepFivePreviewMode(option.value)}
                      className={`rounded-full border px-3 py-1.5 text-xs font-semibold tracking-[0.08em] transition ${
                        active
                          ? "border-[rgba(23,23,23,0.14)] bg-[rgba(23,23,23,0.92)] text-white"
                          : "border-[rgba(17,24,39,0.08)] bg-white text-[#6f655d] hover:border-[rgba(255,106,61,0.26)] hover:text-[#171717]"
                      }`}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {loadingRepoProfileInference ? (
            <div className="mt-4 rounded-[20px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm text-[#746d66]">
              Inspecting the connected repo for install and verify commands...
            </div>
          ) : null}

          {!loadingRepoProfileInference && repoProfileInferenceError ? (
            <div className="mt-4 rounded-[20px] border border-[rgba(255,106,61,0.16)] bg-[rgba(255,106,61,0.08)] p-4">
              <p className="text-sm font-semibold text-[#8f4b31]">Repo inspection needs review</p>
              <p className="mt-1 text-sm leading-6 text-[#8f4b31]">{repoProfileInferenceError}</p>
            </div>
          ) : null}

          {!loadingRepoProfileInference && repoProfileInference ? (
            <div className="mt-4 rounded-[20px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.78)] p-4">
              <p className="text-sm font-semibold text-[#171717]">Detected from the connected repo</p>
              <p className="mt-1 text-sm leading-6 text-[#746d66]">
                {effectiveServiceRepoProfile
                  ? `Saved repo profile values are shown below. Compare them against fresh suggestions from ${
                      repoProfileInference.detected_from.join(", ") || "the repository structure"
                    } before saving edits.`
                  : `Suggested from ${repoProfileInference.detected_from.join(", ") || "the repository structure"}.`}
              </p>
              {repoProfileInference.warnings.length ? (
                <div className="mt-3 space-y-2">
                  {repoProfileInference.warnings.map((warning) => (
                    <p
                      key={warning}
                      className="rounded-[14px] bg-[rgba(255,106,61,0.08)] px-3 py-2 text-sm text-[#8f4b31]"
                    >
                      {warning}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {effectiveStepFiveMode === "single" ? (
            <div className="mt-4 rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.84)] p-5">
              <div className="flex flex-col gap-2">
                <p className="text-sm font-semibold text-[#171717]">Single repo setup</p>
                <p className="text-sm leading-6 text-[#746d66]">
                  For single repo projects, just confirm how the sandbox should verify the repo and
                  give the deployable surface a clean service name. Routing and execution defaults are
                  inferred automatically and can be refined later if needed.
                </p>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <ReadOnlyField
                  label="Repository"
                  value={
                    (effectiveServiceRepository
                      ? `${effectiveServiceRepository.owner}/${effectiveServiceRepository.name}`
                      : null) ??
                    (() => {
                      const selectedRepository = repositories.find(
                        (repository) => repository.id === selectedRepositoryId,
                      );
                      return selectedRepository
                        ? `${selectedRepository.owner}/${selectedRepository.name}`
                        : null;
                    })() ??
                    "Select a repo in step 3"
                  }
                />
                <ReadOnlyField
                  label="Repo profile"
                  value={inferredSingleRepoProfile ? "Already configured" : "Will be created now"}
                />
                <ReadOnlyField label="Mode" value="Single repo" />
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <Field
                  label="Service name"
                  value={serviceName}
                  onChange={setServiceName}
                  placeholder="Web app"
                  helperText={
                    serviceSlug
                      ? `Slug auto-generated as ${serviceSlug}`
                      : "Slug auto-generated from the service name"
                  }
                />
                <SelectField
                  label="Service type"
                  value={serviceType}
                  onChange={(value) =>
                    setServiceType(
                      value as
                        | "frontend"
                        | "backend"
                        | "fullstack"
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
                    { value: "fullstack", label: "Fullstack" },
                    { value: "api", label: "API" },
                    { value: "worker", label: "Worker" },
                    { value: "cron", label: "Cron" },
                    { value: "gateway", label: "Gateway" },
                    { value: "database", label: "Database" },
                    { value: "cache", label: "Cache" },
                    { value: "other", label: "Other" },
                  ]}
                  helperText="Use Fullstack for a true monorepo app deployed together. If frontend and backend deploy separately, create one service per surface instead."
                />
                <Field
                  label="Verify command"
                  value={verifyCommand}
                  onChange={setVerifyCommand}
                  placeholder="npm test or pytest"
                  className="md:col-span-2"
                  helperText={
                    effectiveServiceRepoProfile
                      ? savedProfileSuggestionMatchesVerify
                        ? "Showing the saved repo profile value."
                        : repoProfileInference?.verify_command
                          ? `Showing the saved profile value. Fresh repo suggestion: ${repoProfileInference.verify_command}`
                          : "Showing the saved repo profile value."
                      : repoProfileInference?.verify_command
                        ? "Detected automatically. Review it if this repo has more than one deployable surface."
                        : repoProfileInferenceError
                          ? "We could not infer this automatically from the connected repo."
                          : "This is the main command the sandbox should use to confirm the fix worked."
                  }
                />
                <Field
                  label="Install command"
                  value={installCommand}
                  onChange={setInstallCommand}
                  placeholder="npm install or pip install -r requirements.txt"
                  className="md:col-span-2"
                  helperText={
                    effectiveServiceRepoProfile
                      ? savedProfileSuggestionMatchesInstall
                        ? "Showing the saved repo profile value."
                        : repoProfileInference?.install_command
                          ? `Showing the saved profile value. Fresh repo suggestion: ${repoProfileInference.install_command}`
                          : "Showing the saved repo profile value."
                      : repoProfileInference?.install_command
                        ? "Detected automatically from the connected repo."
                        : repoProfileInferenceError
                          ? "Add the install command manually if repo inspection could not determine it."
                          : undefined
                  }
                />
              </div>

              {hasSecrets ? (
                <RepoSecretMountEditor
                  mode="single"
                  secretRefs={state?.secret_refs ?? []}
                  mounts={repoSecretMounts}
                  onAttachSecret={attachRepoSecretMount}
                  onUpdateMount={updateRepoSecretMount}
                  onRemoveMount={removeRepoSecretMount}
                />
              ) : null}

              <div className="mt-5">
                <ActionButton
                  label={inferredSingleRepoProfile ? "Create project service" : "Create repo profile and service"}
                  onClick={completeSingleRepoSetup}
                  disabled={loading || !canCompleteSingleRepoSetup}
                />
              </div>
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              <div className="rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.84)] p-5">
                <div className="flex flex-col gap-2">
                  <p className="text-sm font-semibold text-[#171717]">Repo profiles</p>
                  <p className="text-sm leading-6 text-[#746d66]">
                    Multi repo projects need a profile for each repo that might run in the sandbox.
                    Create those first, then map them into named services below. Base images, network
                    rules, and other low-level execution settings are inferred automatically unless you
                    need to revisit them later.
                  </p>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <Field
                    label="Install command"
                    value={installCommand}
                    onChange={setInstallCommand}
                    placeholder="pip install -r requirements.txt"
                    className="md:col-span-2"
                    helperText={
                      effectiveServiceRepoProfile
                        ? savedProfileSuggestionMatchesInstall
                          ? "Showing the saved repo profile value."
                          : repoProfileInference?.install_command
                            ? `Showing the saved profile value. Fresh repo suggestion: ${repoProfileInference.install_command}`
                            : "Showing the saved repo profile value."
                        : repoProfileInference?.install_command
                          ? "Detected automatically from the connected repo."
                          : repoProfileInferenceError
                            ? "Add the install command manually if repo inspection could not determine it."
                            : undefined
                    }
                  />
                  <Field
                    label="Verify command"
                    value={verifyCommand}
                    onChange={setVerifyCommand}
                    placeholder="pytest"
                    className="md:col-span-2"
                    helperText={
                      effectiveServiceRepoProfile
                        ? savedProfileSuggestionMatchesVerify
                          ? "Showing the saved repo profile value."
                          : repoProfileInference?.verify_command
                            ? `Showing the saved profile value. Fresh repo suggestion: ${repoProfileInference.verify_command}`
                            : "Showing the saved repo profile value."
                        : repoProfileInference?.verify_command
                          ? "Detected automatically from the connected repo. Adjust it if this repo contains multiple services."
                          : repoProfileInferenceError
                            ? "We could not infer this automatically from the connected repo."
                            : undefined
                    }
                  />
                </div>
                <RepoSecretMountEditor
                  mode="multi"
                  secretRefs={state?.secret_refs ?? []}
                  mounts={repoSecretMounts}
                  onAttachSecret={attachRepoSecretMount}
                  onUpdateMount={updateRepoSecretMount}
                  onRemoveMount={removeRepoSecretMount}
                />
                <div className="mt-4">
                  <ActionButton
                    label="Create repo profile"
                    onClick={createRepoProfile}
                    disabled={loading || !selectedRepositoryId || !verifyCommand.trim()}
                  />
                </div>
              </div>

              <div className="rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.82)] p-5">
                <div className="flex flex-col gap-2">
                  <p className="text-sm font-semibold text-[#171717]">Map deployable services</p>
                  <p className="text-sm leading-6 text-[#746d66]">
                    Attach each app surface to a repo profile, then define the routing hints and
                    dependencies the sandbox needs to understand the full stack.
                  </p>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <Field
                    label="Service name"
                    value={serviceName}
                    onChange={setServiceName}
                    placeholder="Web client"
                    helperText={
                      serviceSlug
                        ? `Slug auto-generated as ${serviceSlug}`
                        : "Slug auto-generated from the service name"
                    }
                  />
                  <SelectField
                    label="Service type"
                    value={serviceType}
                    onChange={(value) =>
                      setServiceType(
                        value as
                          | "frontend"
                          | "backend"
                          | "fullstack"
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
                      { value: "fullstack", label: "Fullstack" },
                      { value: "api", label: "API" },
                      { value: "worker", label: "Worker" },
                      { value: "cron", label: "Cron" },
                      { value: "gateway", label: "Gateway" },
                      { value: "database", label: "Database" },
                      { value: "cache", label: "Cache" },
                      { value: "other", label: "Other" },
                    ]}
                    helperText="If one repo powers multiple deployable surfaces, map each one as its own service instead of choosing a single combined type."
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
                </div>

                <div className="mt-4">
                  <ActionButton
                    label="Add project service"
                    onClick={createProjectService}
                    disabled={loading || !serviceName.trim() || !serviceSlug.trim() || !effectiveServiceRepoProfileId}
                  />
                </div>
              </div>
            </div>
          )}

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.78)] p-5">
              <p className="text-sm font-semibold text-[#171717]">Configured repo profiles</p>
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
            </div>

            <div className="rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.78)] p-5">
              <p className="text-sm font-semibold text-[#171717]">Mapped project services</p>
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
          </div>
        </StepPanel>

        <StepPanel
          step="06"
          stepKey="6"
          title="Enable telemetry and SDK bootstrap"
          description="Create the telemetry credential used for ingest, then choose whether to wire the SDK yourself or let Stimpact open a bootstrap PR against the connected repo."
          complete={hasAnyActiveTelemetryKeys && hasSdkSetup}
          editable={hasAnyActiveTelemetryKeys || hasSdkSetup || Boolean(telemetryKeyPlaintext)}
          isEditing={editingStepKey === "6"}
          editDisabled={Boolean(editingStepKey) && editingStepKey !== "6"}
          onEdit={() => beginStepEditing("6")}
          onCancelEdit={cancelStepEditing}
          sectionRef={(node) => {
            stepRefs.current["6"] = node;
          }}
        >
          <div className="rounded-[28px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.84)] overflow-hidden">
            <div className="px-6 py-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-[#171717]">Telemetry key</p>
                  <p className="mt-1 max-w-3xl text-sm leading-6 text-[#746d66]">
                    Create the project-scoped telemetry credential first. Your app will use it for telemetry
                    delivery and heartbeat verification after the SDK is deployed.
                  </p>
                </div>
                <span className="rounded-full bg-[rgba(29,26,24,0.08)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#6f655d]">
                  {sdkStatusLabel}
                </span>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                <Field
                  label={sdkUsesBrowserCredential ? "Browser key name" : "API key name"}
                  value={telemetryKeyName}
                  onChange={setTelemetryKeyName}
                  placeholder="Production telemetry key"
                />
                <ActionButton
                  label={
                    activeApiKeys.length || activeBrowserKeys.length
                      ? `Generate another ${sdkCredentialLabel}`
                      : `Create telemetry ${sdkCredentialLabel}`
                  }
                  onClick={createTelemetryApiKey}
                  disabled={loading || !telemetryKeyName.trim()}
                  variant={activeApiKeys.length || activeBrowserKeys.length ? "secondary" : "primary"}
                />
              </div>
              <div className="mt-4 flex flex-wrap gap-2.5">
                <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(17,24,39,0.08)] bg-[rgba(247,242,236,0.7)] px-3.5 py-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a8178]">
                    Active keys
                  </span>
                  <span className="text-sm font-semibold text-[#171717]">
                    {activeApiKeys.length + activeBrowserKeys.length}
                  </span>
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(17,24,39,0.08)] bg-[rgba(247,242,236,0.7)] px-3.5 py-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a8178]">
                    Target service
                  </span>
                  <span className="text-sm font-semibold text-[#171717]">{effectiveSdkServiceName}</span>
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(17,24,39,0.08)] bg-[rgba(247,242,236,0.7)] px-3.5 py-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a8178]">
                    Environment
                  </span>
                  <span className="text-sm font-semibold text-[#171717]">
                    {sdkEnvironment.trim() || "production"}
                  </span>
                </div>
              </div>
              {telemetryKeyPlaintext ? (
                <div className="mt-4 rounded-[18px] border border-[rgba(34,197,94,0.16)] bg-[rgba(240,253,244,0.92)] px-4 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <p className="text-sm font-semibold text-[#166534]">
                      {`New plaintext ${sdkCredentialLabel}`}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        void copyTelemetryKeyToClipboard();
                      }}
                      className="inline-flex items-center gap-2 rounded-full border border-[rgba(22,101,52,0.16)] bg-white/80 px-3 py-1.5 text-xs font-semibold text-[#166534] transition hover:border-[rgba(22,101,52,0.24)] hover:bg-white"
                    >
                      <CopyMiniGlyph />
                      {copiedTelemetryKey ? "Copied" : "Copy key"}
                    </button>
                  </div>
                  <p className="mt-1 break-all font-mono text-xs leading-6 text-[#166534]">
                    {telemetryKeyPlaintext}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-[#4d7c0f]">
                    This plaintext value is only shown here right after creation. Save it in your
                    deployment environment before leaving the page.
                  </p>
                </div>
              ) : null}
            </div>

            <div className="border-t border-[rgba(17,24,39,0.08)] px-6 py-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-[#171717]">Choose setup mode</p>
                  <p className="mt-1 max-w-3xl text-sm leading-6 text-[#746d66]">
                    Pick the path you want. Automatic mode attempts the SDK integration for you and
                    prepares a reviewed PR preview. Manual mode shows the exact code and config to add
                    yourself. You can switch between them at any time.
                  </p>
                </div>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <button
                  type="button"
                  onClick={chooseAutomaticSdkMode}
                  aria-pressed={sdkSetupMode === "automatic"}
                  className={`group relative overflow-hidden rounded-[22px] border px-5 py-5 text-left transition cursor-pointer ${
                    sdkSetupMode === "automatic"
                      ? "border-[rgba(73,133,255,0.45)] bg-[linear-gradient(145deg,rgba(246,250,255,0.98)_0%,rgba(226,236,248,0.96)_42%,rgba(214,226,242,0.95)_100%)] shadow-[0_18px_36px_rgba(50,98,180,0.16)] ring-2 ring-[rgba(76,128,235,0.18)]"
                      : "border-[rgba(114,138,173,0.24)] bg-[linear-gradient(145deg,rgba(248,251,255,0.94)_0%,rgba(233,240,249,0.88)_52%,rgba(222,232,244,0.84)_100%)] hover:-translate-y-0.5 hover:border-[rgba(73,133,255,0.28)] hover:shadow-[0_16px_30px_rgba(47,84,150,0.10)]"
                  }`}
                >
                  <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.42)_0%,rgba(255,255,255,0.08)_32%,rgba(255,255,255,0)_100%)]" />
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <span
                        className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition ${
                          sdkSetupMode === "automatic"
                            ? "border-[rgba(62,116,223,0.50)] bg-[rgba(73,133,255,0.10)]"
                            : "border-[rgba(83,103,132,0.18)] bg-[rgba(255,255,255,0.92)]"
                        }`}
                      >
                        <span
                          className={`inline-flex h-2.5 w-2.5 rounded-full transition ${
                            sdkSetupMode === "automatic" ? "bg-[#2e6fe8]" : "bg-transparent"
                          }`}
                        />
                      </span>
                      <div className="flex flex-col gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="inline-flex rounded-full bg-[rgba(58,79,109,0.06)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#67758a]">
                            Automatic
                          </span>
                        </div>
                      <p className="text-sm font-semibold text-[#171717]">Automatic SDK installation PR</p>
                      </div>
                    </div>
                    <span
                      className={`inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                        sdkSetupMode === "automatic"
                          ? "text-[#2457b8]"
                          : "text-[#6a7688] transition group-hover:text-[#2457b8]"
                      }`}
                    >
                      {sdkSetupMode === "automatic" ? "Active mode" : "Click to choose"}
                      <span className={`${sdkSetupMode === "automatic" ? "" : "transition group-hover:translate-x-0.5"}`}>
                        {sdkSetupMode === "automatic" ? "✓" : "→"}
                      </span>
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[#746d66]">
                    First choose this path, then explicitly start the automatic attempt below when you
                    are ready.
                  </p>
                  <div className="mt-3 rounded-[16px] bg-[rgba(73,133,255,0.08)] px-3 py-2 text-xs font-medium text-[#355e9f]">
                    Best when you want Stimpact to inspect the repo and draft a reviewable PR preview.
                  </div>
                </button>
                <button
                  type="button"
                  onClick={openManualSdkMode}
                  aria-pressed={sdkSetupMode === "manual"}
                  className={`group relative overflow-hidden rounded-[22px] border px-5 py-5 text-left transition cursor-pointer ${
                    sdkSetupMode === "manual"
                      ? "border-[rgba(73,133,255,0.45)] bg-[linear-gradient(145deg,rgba(246,250,255,0.98)_0%,rgba(226,236,248,0.96)_42%,rgba(214,226,242,0.95)_100%)] shadow-[0_18px_36px_rgba(50,98,180,0.16)] ring-2 ring-[rgba(76,128,235,0.18)]"
                      : "border-[rgba(114,138,173,0.24)] bg-[linear-gradient(145deg,rgba(248,251,255,0.94)_0%,rgba(233,240,249,0.88)_52%,rgba(222,232,244,0.84)_100%)] hover:-translate-y-0.5 hover:border-[rgba(73,133,255,0.28)] hover:shadow-[0_16px_30px_rgba(47,84,150,0.10)]"
                  }`}
                >
                  <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.42)_0%,rgba(255,255,255,0.08)_32%,rgba(255,255,255,0)_100%)]" />
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <span
                        className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition ${
                          sdkSetupMode === "manual"
                            ? "border-[rgba(62,116,223,0.50)] bg-[rgba(73,133,255,0.10)]"
                            : "border-[rgba(83,103,132,0.18)] bg-[rgba(255,255,255,0.92)]"
                        }`}
                      >
                        <span
                          className={`inline-flex h-2.5 w-2.5 rounded-full transition ${
                            sdkSetupMode === "manual" ? "bg-[#2e6fe8]" : "bg-transparent"
                          }`}
                        />
                      </span>
                      <div className="flex flex-col gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="inline-flex rounded-full bg-[rgba(58,79,109,0.06)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#67758a]">
                            Manual
                          </span>
                        </div>
                        <p className="text-sm font-semibold text-[#171717]">Manual installation mode</p>
                      </div>
                    </div>
                    <span
                      className={`inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                        sdkSetupMode === "manual"
                          ? "text-[#2457b8]"
                          : "text-[#6a7688] transition group-hover:text-[#2457b8]"
                      }`}
                    >
                      {sdkSetupMode === "manual" ? "Active mode" : "Click to choose"}
                      <span className={`${sdkSetupMode === "manual" ? "" : "transition group-hover:translate-x-0.5"}`}>
                        {sdkSetupMode === "manual" ? "✓" : "→"}
                      </span>
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[#746d66]">
                    Use the generated framework guidance, environment variables, and starter code to
                    add the SDK yourself in the correct runtime entrypoint.
                  </p>
                  <div className="mt-3 rounded-[16px] bg-[rgba(73,133,255,0.08)] px-3 py-2 text-xs font-medium text-[#355e9f]">
                    Best when you want full control over where and how the SDK is added.
                  </div>
                </button>
              </div>
            </div>

            <div className="px-6 pb-5 pt-5">
              {sdkSetupMode === "automatic" ? (
                <div className="space-y-5">
                  <div className="relative overflow-hidden rounded-[30px] border border-[rgba(44,97,255,0.16)] bg-[linear-gradient(135deg,rgba(255,248,244,0.98)_0%,rgba(255,255,255,0.98)_38%,rgba(242,247,255,0.98)_100%)] px-6 py-6 shadow-[0_28px_70px_rgba(33,97,255,0.10)]">
                    <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,#ff6a3d_0%,#ff8a3d_28%,#2d7ff9_72%,#173fbe_100%)]" />
                    <div className="pointer-events-none absolute -left-10 top-6 h-32 w-32 rounded-full bg-[rgba(255,106,61,0.18)] blur-3xl" />
                    <div className="pointer-events-none absolute right-0 top-0 h-40 w-40 rounded-full bg-[rgba(45,127,249,0.16)] blur-3xl" />
                    <div className="relative">
                      <div className="flex flex-wrap items-start justify-between gap-5">
                        <div className="max-w-3xl">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#ff6a3d]">
                            Agent-guided setup
                          </p>
                          <h3 className="mt-2 text-[1.25rem] font-semibold tracking-[-0.02em] text-[#13213a]">
                            Stimpact can configure this SDK path for you
                          </h3>
                          <p className="mt-2 text-sm leading-6 text-[#49566c]">
                            The agent inspects the connected codebase, selects the safest integration
                            path, and prepares a reviewable PR preview before anything is written.
                          </p>
                        </div>
                        {sdkSetupMode === "automatic" && !sdkAutomaticRequested ? (
                          <ActionButton
                            label="Start automatic attempt"
                            onClick={startAutomaticSdkWorkflow}
                            disabled={loading || !sdkTargetRepositoryId || !platformBaseUrl}
                          />
                        ) : (
                          <div
                            className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] ${
                              sdkAutomationStage === "planning" || sdkAutomationStage === "previewing"
                                ? "bg-[rgba(255,106,61,0.12)] text-[#d64e1d]"
                                : sdkAutomationStage === "ready"
                                  ? "bg-[linear-gradient(180deg,#2d7ff9,#173fbe)] text-white"
                                  : "bg-[rgba(19,33,58,0.08)] text-[#516075]"
                            }`}
                          >
                            <span
                              className={`inline-flex h-2.5 w-2.5 rounded-full ${
                                sdkAutomationStage === "planning" || sdkAutomationStage === "previewing"
                                  ? "animate-pulse bg-[#ff6a3d]"
                                  : sdkAutomationStage === "ready"
                                    ? "bg-white"
                                    : "bg-[rgba(19,33,58,0.26)]"
                              }`}
                            />
                            {sdkAutomationStageLabel}
                          </div>
                        )}
                      </div>

                      <div className="mt-6 flex flex-wrap gap-x-8 gap-y-4 border-y border-[rgba(19,33,58,0.08)] py-4">
                        {sdkAutomationSummaryItems.map((item) => (
                          <div key={item.label} className="min-w-[11rem] flex-1">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#6f7b90]">
                              {item.label}
                            </p>
                            <p className="mt-1.5 text-sm font-semibold text-[#13213a]">{item.value}</p>
                          </div>
                        ))}
                        <label className="min-w-[11rem] flex-1 sm:max-w-[14rem]">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#6f7b90]">
                            Environment
                          </span>
                          <input
                            value={sdkEnvironment}
                            onChange={(event) => setSdkEnvironment(event.target.value)}
                            placeholder="production"
                            className="mt-1.5 w-full rounded-[14px] border border-[rgba(45,127,249,0.18)] bg-white/92 px-4 py-3 text-sm text-[#13213a] shadow-[0_6px_20px_rgba(45,127,249,0.08)] outline-none transition placeholder:text-[#8f99aa] focus:border-[rgba(255,106,61,0.48)] focus:shadow-[0_0_0_4px_rgba(255,106,61,0.10)]"
                          />
                        </label>
                      </div>

                      <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.95fr)] xl:divide-x xl:divide-[rgba(19,33,58,0.08)]">
                        <div className="xl:pr-8">
                          <div className="flex items-start gap-4">
                            <span
                              className={`inline-flex h-12 w-12 items-center justify-center rounded-full border ${
                                sdkAutomationStage === "planning" || sdkAutomationStage === "previewing"
                                  ? "border-[rgba(255,106,61,0.24)] bg-[rgba(255,106,61,0.10)]"
                                  : sdkAutomationStage === "ready"
                                    ? "border-[rgba(45,127,249,0.24)] bg-[rgba(45,127,249,0.12)]"
                                    : sdkAutomationStage === "manual_only"
                                      ? "border-[rgba(19,33,58,0.12)] bg-[rgba(19,33,58,0.06)]"
                                      : "border-[rgba(19,33,58,0.12)] bg-white/90"
                              }`}
                            >
                              <span
                                className={`inline-flex h-5 w-5 rounded-full ${
                                  sdkAutomationStage === "planning" || sdkAutomationStage === "previewing"
                                    ? "animate-spin border-2 border-[rgba(255,106,61,0.25)] border-t-[#ff6a3d]"
                                    : sdkAutomationStage === "ready"
                                      ? "bg-[linear-gradient(180deg,#2d7ff9,#173fbe)]"
                                      : sdkAutomationStage === "manual_only"
                                        ? "bg-[rgba(19,33,58,0.24)]"
                                        : "bg-[rgba(19,33,58,0.16)]"
                                }`}
                              />
                            </span>
                            <div>
                              <p className="text-sm font-semibold text-[#13213a]">Automatic setup activity</p>
                              <p className="text-xs uppercase tracking-[0.18em] text-[#6f7b90]">
                                {sdkAutomationStageLabel}
                              </p>
                            </div>
                          </div>

                          <div className="mt-4 flex flex-wrap items-center gap-2">
                            <span className="rounded-full bg-[rgba(19,33,58,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#516075]">
                              {sdkCompletedWorkflowCount}/{automaticWorkflowItems.length} steps complete
                            </span>
                            {(sdkAutomationStage === "planning" || sdkAutomationStage === "previewing") && (
                              <span className="rounded-full bg-[rgba(255,106,61,0.10)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#d64e1d]">
                                Live now
                              </span>
                            )}
                          </div>

                          <div className="mt-4 border-l-4 border-[#ff6a3d] pl-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#ff6a3d]">
                              Current agent focus
                            </p>
                            <p
                              className={`mt-2 text-base font-semibold text-[#13213a] ${
                                sdkAutomationStage === "planning" || sdkAutomationStage === "previewing"
                                  ? "animate-pulse"
                                  : ""
                              }`}
                            >
                              {sdkActiveThought}
                            </p>
                          </div>

                          <div className="mt-5 overflow-hidden rounded-full bg-[rgba(23,63,190,0.08)]">
                            <div
                              className={`h-2 rounded-full transition-all duration-500 ${
                                sdkWorkflowProgressTone === "active"
                                  ? "animate-pulse bg-[linear-gradient(90deg,#ff6a3d_0%,#ff9447_28%,#2d7ff9_78%,#173fbe_100%)]"
                                  : sdkWorkflowProgressTone === "complete"
                                    ? "bg-[linear-gradient(90deg,#2d7ff9,#173fbe)]"
                                    : sdkWorkflowProgressTone === "blocked"
                                      ? "bg-[rgba(19,33,58,0.24)]"
                                      : "bg-transparent"
                              }`}
                              style={{ width: `${sdkWorkflowProgressPercent}%` }}
                            />
                          </div>

                          {sdkVisibleWorkflowItems.length ? (
                            <div className="mt-5 flex flex-wrap gap-2">
                              {sdkVisibleWorkflowItems.map((item) => (
                                <div
                                  key={item.id}
                                  className={`inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold ${
                                    item.state === "complete"
                                      ? "bg-[rgba(45,127,249,0.10)] text-[#173fbe]"
                                      : item.state === "active"
                                        ? "bg-[rgba(255,106,61,0.12)] text-[#d64e1d]"
                                        : "bg-[rgba(19,33,58,0.08)] text-[#516075]"
                                  }`}
                                >
                                  <span
                                    className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${
                                      item.state === "complete"
                                        ? "bg-[linear-gradient(180deg,#2d7ff9,#173fbe)] text-white"
                                        : item.state === "active"
                                          ? "bg-[linear-gradient(180deg,#ff6a3d,#ff7d3d)] text-white animate-pulse"
                                          : "bg-[rgba(19,33,58,0.12)] text-[#516075]"
                                    }`}
                                  >
                                    {item.state === "complete" ? "✓" : item.state === "active" ? "•" : "!"}
                                  </span>
                                  <span>{item.label}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="mt-5 text-sm leading-6 text-[#6f7b90]">
                              Start the automatic attempt to watch each step appear here as the agent progresses.
                            </p>
                          )}
                        </div>

                        <div className="xl:pl-8">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-[#13213a]">Live agent feed</p>
                            </div>
                            {(sdkAutomationStage === "planning" || sdkAutomationStage === "previewing") && (
                              <span className="rounded-full bg-[rgba(45,127,249,0.12)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#173fbe]">
                                Live
                              </span>
                            )}
                          </div>

                          <div className="mt-5 space-y-4">
                            {sdkVisibleAgentFeedItems.map((item, index) => (
                              <div
                                key={`${index}-${item.thought}`}
                                className={`rounded-[18px] px-4 py-3 ${
                                  item.state === "active"
                                    ? "bg-[rgba(255,106,61,0.08)]"
                                    : item.state === "complete"
                                      ? "bg-[rgba(45,127,249,0.08)]"
                                      : item.state === "blocked"
                                        ? "bg-[rgba(19,33,58,0.07)]"
                                        : "bg-[rgba(19,33,58,0.04)]"
                                }`}
                              >
                                <div className="flex items-start gap-3">
                                  <span
                                    className={`mt-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full text-[10px] font-semibold ${
                                      item.state === "active"
                                        ? "bg-[linear-gradient(180deg,#ff6a3d,#ff7d3d)] text-white animate-pulse"
                                        : item.state === "complete"
                                          ? "bg-[linear-gradient(180deg,#2d7ff9,#173fbe)] text-white"
                                          : item.state === "blocked"
                                            ? "bg-[rgba(19,33,58,0.10)] text-[#516075]"
                                            : "bg-[rgba(19,33,58,0.06)] text-[#6f7b90]"
                                    }`}
                                  >
                                    {item.state === "complete" ? "✓" : item.state === "blocked" ? "!" : "•"}
                                  </span>
                                  <div className="min-w-0">
                                    <p className="text-sm font-medium leading-6 text-[#13213a]">{item.thought}</p>
                                    <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#6f7b90]">
                                      {item.state === "active"
                                        ? "Working now"
                                        : item.state === "complete"
                                          ? "Completed"
                                          : item.state === "blocked"
                                            ? "Stopped"
                                            : "Queued"}
                                    </p>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  {!platformBaseUrl ? (
                    <p className="rounded-[16px] bg-[rgba(255,106,61,0.08)] px-4 py-3 text-sm text-[#8f4b31]">
                      Set `AGENT_PLATFORM_PUBLIC_BASE_URL` before automatic setup so the generated
                      SDK config points at the correct public Stimpact URL.
                    </p>
                  ) : null}
                  {loadingSdkBootstrapPlan ? (
                    <p className="rounded-[16px] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm text-[#746d66]">
                      Inspecting the selected repository for supported SDK bootstrap surfaces...
                    </p>
                  ) : sdkBootstrapPlan?.warnings.length ? (
                    <div className="space-y-2">
                      {sdkBootstrapPlan.warnings.map((warning) => (
                        <p
                          key={warning}
                          className="rounded-[16px] bg-[rgba(255,106,61,0.08)] px-4 py-3 text-sm text-[#8f4b31]"
                        >
                          {warning}
                        </p>
                      ))}
                    </div>
                  ) : null}
                  {sdkRequiresConfirmationMessage ? (
                    <p className="rounded-[16px] border border-[rgba(45,127,249,0.14)] bg-[rgba(242,247,255,0.92)] px-4 py-3 text-sm text-[#214a8b]">
                      {sdkRequiresConfirmationMessage}
                    </p>
                  ) : null}
                  {sdkBootstrapPlan?.strategies.length ? (
                    <div className="grid gap-3">
                      {sdkBootstrapPlan.strategies.map((strategy) => {
                        const selected = selectedSdkStrategy?.id === strategy.id;
                        return (
                          <button
                            key={strategy.id}
                            type="button"
                            onClick={() => {
                              setSelectedSdkStrategyId(strategy.id);
                              setDismissedSdkPreviewStrategyId(null);
                            }}
                            className={`rounded-[20px] border px-4 py-4 text-left transition ${
                              selected
                                ? "border-[rgba(23,23,23,0.18)] bg-white shadow-[0_14px_28px_rgba(15,23,42,0.06)]"
                                : "border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.68)] hover:border-[rgba(255,106,61,0.18)] hover:bg-white"
                            }`}
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-sm font-semibold text-[#171717]">{strategy.framework}</p>
                              <span
                                className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                                  strategy.source === "llm"
                                    ? "bg-[rgba(255,106,61,0.12)] text-[#a54d2f]"
                                    : "bg-[rgba(23,23,23,0.06)] text-[#5f564f]"
                                }`}
                              >
                                {strategy.source === "llm" ? "Model-assisted" : "Deterministic"}
                              </span>
                              <span
                                className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                                  strategy.pr_supported
                                    ? "bg-[linear-gradient(180deg,#22c55e,#16a34a)] text-white"
                                    : "bg-[rgba(29,26,24,0.08)] text-[#6f655d]"
                                }`}
                              >
                                {strategy.pr_supported ? `${strategy.confidence} confidence` : "Manual only"}
                              </span>
                            </div>
                            <p className="mt-2 text-sm leading-6 text-[#746d66]">{strategy.summary}</p>
                            {strategy.entrypoints.length ? (
                              <p className="mt-2 text-xs leading-5 text-[#8a8178]">
                                Entrypoint: {strategy.entrypoints.join(", ")}
                              </p>
                            ) : null}
                            {strategy.confidence_reason ? (
                              <p className="mt-2 text-xs leading-5 text-[#8a8178]">
                                Why this surface: {strategy.confidence_reason}
                              </p>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="rounded-[16px] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm text-[#746d66]">
                      No supported automatic JavaScript or Python bootstrap surface was detected for
                      this repository.
                    </p>
                  )}
                  {sdkAutomaticRunStarted && selectedSdkStrategy && !sdkBootstrapPreview ? (
                    <div className="rounded-[20px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.78)] px-4 py-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold text-[#171717]">Selected strategy review</p>
                        <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#5f564f]">
                          {sdkStrategyConfidenceLabel}
                        </span>
                        <span
                          className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                            sdkPatchAttempt?.verification.status === "failed"
                              ? "bg-[rgba(255,106,61,0.12)] text-[#a54d2f]"
                              : selectedSdkStrategy.pr_supported
                              ? "bg-[linear-gradient(180deg,#22c55e,#16a34a)] text-white"
                              : "bg-[rgba(255,106,61,0.12)] text-[#a54d2f]"
                          }`}
                        >
                          {sdkPatchAttempt?.verification.status === "failed"
                            ? "Verification blocked"
                            : selectedSdkStrategy.pr_supported
                              ? "Preview can be generated"
                              : "Preview blocked"}
                        </span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-[#5f6470]">{selectedSdkStrategy.summary}</p>
                      {selectedSdkStrategy.confidence_reason ? (
                        <p className="mt-3 text-sm leading-6 text-[#5f6470]">
                          <span className="font-semibold text-[#171717]">Why this surface:</span>{" "}
                          {selectedSdkStrategy.confidence_reason}
                        </p>
                      ) : null}
                      {sdkSelectedStrategyBlockers.length ? (
                        <div className="mt-4 rounded-[16px] border border-[rgba(255,106,61,0.14)] bg-[rgba(255,247,242,0.9)] px-4 py-4">
                          <p className="text-sm font-semibold text-[#171717]">Why automatic stopped here</p>
                          <div className="mt-3 space-y-2">
                            {sdkSelectedStrategyBlockers.map((item) => (
                              <p key={item} className="text-sm leading-6 text-[#8f4b31]">
                                {item}
                              </p>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {!sdkAutomaticRunStarted ? (
                    <p className="rounded-[16px] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm text-[#746d66]">
                      Start the automatic attempt and Stimpact will inspect the repository, choose the
                      safest supported surface, and show the verified preview here.
                    </p>
                  ) : loadingSdkBootstrapPreview ? (
                    <p className="rounded-[16px] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm text-[#746d66]">
                      Building the exact bootstrap PR preview for the selected strategy and verifying it in a temp checkout...
                    </p>
                  ) : sdkBootstrapPreview ? (
                    <>
                      <div className="rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(247,250,255,0.92))] px-5 py-5 shadow-[0_16px_34px_rgba(15,23,42,0.06)]">
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div className="max-w-3xl">
                            <p className="text-sm font-semibold text-[#171717]">Review generated SDK patch</p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#5f564f]">
                                {sdkBootstrapPreview.strategy.framework}
                              </span>
                              <span
                                className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                                  sdkBootstrapPreview.strategy.source === "llm"
                                    ? "bg-[rgba(255,106,61,0.12)] text-[#a54d2f]"
                                    : "bg-[rgba(23,23,23,0.06)] text-[#5f564f]"
                                }`}
                              >
                                {sdkBootstrapPreview.strategy.source === "llm"
                                  ? "Model-assisted"
                                  : "Deterministic"}
                              </span>
                              <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#5f564f]">
                                {sdkBootstrapPreview.strategy.confidence} confidence
                              </span>
                              <span
                                className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                                  sdkBootstrapPreview.attempt.verification.status === "passed"
                                    ? "bg-[linear-gradient(180deg,#22c55e,#16a34a)] text-white"
                                    : sdkBootstrapPreview.attempt.verification.status === "needs_review"
                                      ? "bg-[rgba(45,127,249,0.12)] text-[#173fbe]"
                                      : "bg-[rgba(255,106,61,0.12)] text-[#a54d2f]"
                                }`}
                              >
                                {sdkBootstrapPreview.attempt.verification.status === "passed"
                                  ? "Verification passed"
                                  : sdkBootstrapPreview.attempt.verification.status === "needs_review"
                                    ? "Needs review"
                                    : "Verification failed"}
                              </span>
                            </div>
                            <p className="mt-3 text-sm leading-6 text-[#5f6470]">
                              {sdkBootstrapPreview.strategy.summary}
                            </p>
                            {sdkBootstrapPreview.attempt.verification.summary ? (
                              <p className="mt-2 text-sm leading-6 text-[#5f6470]">
                                <span className="font-semibold text-[#171717]">Verification:</span>{" "}
                                {sdkBootstrapPreview.attempt.verification.summary}
                              </p>
                            ) : null}
                            {sdkBootstrapPreview.strategy.confidence_reason ? (
                              <p className="mt-2 text-sm leading-6 text-[#5f6470]">
                                <span className="font-semibold text-[#171717]">Why this surface:</span>{" "}
                                {sdkBootstrapPreview.strategy.confidence_reason}
                              </p>
                            ) : null}
                          </div>
                          <div className="min-w-[16rem] space-y-2 text-sm text-[#5f6470]">
                            <p>
                              <span className="font-semibold text-[#171717]">Branch:</span>{" "}
                              {sdkBootstrapPreview.pull_request.branch_name}
                            </p>
                            <p>
                              <span className="font-semibold text-[#171717]">PR title:</span>{" "}
                              {sdkBootstrapPreview.pull_request.title}
                            </p>
                            <p>
                              <span className="font-semibold text-[#171717]">Entrypoint:</span>{" "}
                              {sdkEntryPointLabel}
                            </p>
                          </div>
                        </div>

                        <div className="mt-4 flex flex-wrap gap-2">
                          <span className="rounded-full bg-[rgba(45,127,249,0.10)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#173fbe]">
                            {sdkBootstrapPreview.strategy.planned_files.length} files to update
                          </span>
                          <span className="rounded-full bg-[rgba(45,127,249,0.10)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#173fbe]">
                            {sdkPreviewDiffFiles.reduce((total, file) => total + file.additions, 0)} additions
                          </span>
                          <span className="rounded-full bg-[rgba(255,106,61,0.10)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#a54d2f]">
                            {sdkPreviewDiffFiles.reduce((total, file) => total + file.deletions, 0)} removals
                          </span>
                          <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f564f]">
                            Failure stage: {sdkBootstrapPreview.attempt.failure_stage ?? "none"}
                          </span>
                        </div>

                        {sdkBootstrapPlan?.requires_confirmation ? (
                          <p className="mt-4 text-sm leading-6 text-[#214a8b]">
                            Review required: this repository exposed multiple plausible SDK surfaces, so
                            the agent is showing you the chosen target before PR creation.
                          </p>
                        ) : null}
                        {sdkBootstrapPreview.attempt.warnings.length ? (
                          <div className="mt-4 space-y-2 text-sm leading-6 text-[#8f4b31]">
                            {sdkBootstrapPreview.attempt.warnings.map((item) => (
                              <p key={item}>
                                <span className="font-semibold text-[#171717]">Warning:</span> {item}
                              </p>
                            ))}
                          </div>
                        ) : null}
                        {sdkBootstrapPreview.strategy.blockers.length ? (
                          <div className="mt-4 space-y-2 text-sm leading-6 text-[#8f4b31]">
                            {sdkBootstrapPreview.strategy.blockers.map((item) => (
                              <p key={item}>
                                <span className="font-semibold text-[#171717]">Guardrail:</span> {item}
                              </p>
                            ))}
                          </div>
                        ) : null}

                        <div className="mt-5 grid gap-4 md:grid-cols-3">
                          {sdkPreviewNextSteps.map((item, index) => (
                            <div key={item.title} className="border-l-2 border-[rgba(45,127,249,0.18)] pl-4">
                              <p className="text-sm font-semibold text-[#171717]">
                                {index + 1}. {item.title}
                              </p>
                              <p className="mt-1 text-sm leading-6 text-[#5f6470]">{item.detail}</p>
                            </div>
                          ))}
                        </div>

                        {sdkPreviewAttempts.length > 1 ? (
                          <div className="mt-5">
                            {sdkAttemptHistorySummary ? (
                              <p className="text-sm leading-6 text-[#5f6470]">{sdkAttemptHistorySummary}</p>
                            ) : null}
                            <div className="mt-3 flex flex-wrap gap-2">
                              {sdkPreviewAttempts.map((item) => (
                                <span
                                  key={`${item.candidate_id ?? item.strategy_id}-${item.attempt_number ?? 0}`}
                                  className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                                    item.change_request_allowed
                                      ? "bg-[linear-gradient(180deg,#22c55e,#16a34a)] text-white"
                                      : item.preview_available
                                        ? "bg-[rgba(45,127,249,0.12)] text-[#173fbe]"
                                        : "bg-[rgba(255,106,61,0.12)] text-[#a54d2f]"
                                  }`}
                                >
                                  Attempt {item.attempt_number ?? "?"}:{" "}
                                  {item.change_request_allowed
                                    ? "reviewable"
                                    : item.preview_available
                                      ? "preview"
                                      : "rejected"}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>

                      {(sdkBootstrapPreview.attempt.verification.command ||
                        sdkBootstrapPreview.attempt.verification.output ||
                        sdkBootstrapPreview.pull_request.description) && (
                        <div className="grid gap-4 lg:grid-cols-3">
                          {sdkBootstrapPreview.attempt.verification.command ? (
                            <CodePanel
                              title="Verification command"
                              code={sdkBootstrapPreview.attempt.verification.command}
                            />
                          ) : null}
                          {sdkBootstrapPreview.attempt.verification.output ? (
                            <CodePanel
                              title="Verification output"
                              code={sdkBootstrapPreview.attempt.verification.output}
                            />
                          ) : null}
                          <CodePanel title="Draft PR body" code={sdkBootstrapPreview.pull_request.description} />
                        </div>
                      )}

                      <DiffReviewPanel
                        title="Patch review"
                        files={sdkPreviewDiffFiles}
                        plannedFiles={sdkBootstrapPreview.strategy.planned_files}
                        rawDiff={sdkBootstrapPreview.patch_diff}
                      />
                    </>
                  ) : automaticSdkAvailable ? (
                    <p className="rounded-[16px] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm text-[#746d66]">
                      Choose a supported strategy and Stimpact will prepare the PR preview here.
                    </p>
                  ) : (
                    <p className="rounded-[16px] bg-[rgba(255,106,61,0.08)] px-4 py-3 text-sm text-[#8f4b31]">
                      Automatic setup is not available for the selected surface yet. Switch to manual
                      mode for the exact install instructions instead.
                    </p>
                  )}
                  {sdkAutomaticRunStarted ? (
                    <div className="flex flex-wrap gap-3">
                      <ActionButton
                        label="Approve and create PR"
                        onClick={createSdkBootstrapChangeRequest}
                        disabled={
                          loading ||
                          !sdkTargetRepositoryId ||
                          !platformBaseUrl ||
                          !selectedSdkStrategy ||
                          !selectedSdkStrategy.pr_supported ||
                          !sdkBootstrapPreview ||
                          !sdkBootstrapPreview.attempt.change_request_allowed ||
                          loadingSdkBootstrapPreview
                        }
                      />
                      <ActionButton
                        label="Switch to manual mode"
                        onClick={dismissSdkBootstrapPreview}
                        disabled={loading || loadingSdkBootstrapPreview}
                        variant="secondary"
                      />
                      {onboardingState?.sdk_setup_change_request_url ? (
                        <a
                          href={onboardingState.sdk_setup_change_request_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center rounded-full border border-[rgba(29,26,24,0.08)] bg-white px-4 py-2 text-sm font-semibold text-[#171717] transition hover:border-[rgba(255,106,61,0.22)] hover:bg-[#fff8f3]"
                        >
                          Open current PR
                        </a>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="space-y-5">
                  {loadingSdkBootstrapPlan ? (
                    <div className="space-y-4">
                      <div className="flex items-start gap-3">
                        <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[rgba(45,127,249,0.10)]">
                          <span className="inline-flex h-3 w-3 animate-pulse rounded-full bg-[linear-gradient(180deg,#2d7ff9,#173fbe)]" />
                        </span>
                        <div>
                          <p className="text-sm font-semibold text-[#17385d]">
                            Preparing manual instructions
                          </p>
                          <p className="mt-1 text-sm leading-6 text-[#5f6470]">
                            Stimpact is inspecting the connected repository, finding the runtime
                            entrypoint, and preparing the exact install, env, and code steps for you.
                          </p>
                        </div>
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center gap-3">
                          <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[rgba(45,127,249,0.10)] text-[11px] font-semibold text-[#173fbe]">
                            1
                          </span>
                          <div className="h-3 w-48 animate-pulse rounded-full bg-[rgba(23,56,93,0.10)]" />
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[rgba(45,127,249,0.10)] text-[11px] font-semibold text-[#173fbe]">
                            2
                          </span>
                          <div className="h-3 w-64 animate-pulse rounded-full bg-[rgba(23,56,93,0.08)]" />
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[rgba(45,127,249,0.10)] text-[11px] font-semibold text-[#173fbe]">
                            3
                          </span>
                          <div className="h-3 w-56 animate-pulse rounded-full bg-[rgba(23,56,93,0.08)]" />
                        </div>
                      </div>
                    </div>
                  ) : selectedSdkStrategy ? (
                    <>
                      <div className="flex flex-wrap gap-2.5">
                        <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(17,24,39,0.08)] bg-[rgba(247,242,236,0.7)] px-3.5 py-2">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a8178]">
                            Framework
                          </span>
                          <span className="text-sm font-semibold text-[#171717]">
                            {selectedSdkStrategy.framework}
                          </span>
                        </div>
                        <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(17,24,39,0.08)] bg-[rgba(247,242,236,0.7)] px-3.5 py-2">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a8178]">
                            Entrypoint
                          </span>
                          <span className="text-sm font-semibold text-[#171717]">{sdkEntryPointLabel}</span>
                        </div>
                        <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(17,24,39,0.08)] bg-[rgba(247,242,236,0.7)] px-3.5 py-2">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a8178]">
                            Service
                          </span>
                          <span className="text-sm font-semibold text-[#171717]">
                            {effectiveSdkServiceName}
                          </span>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-[#17385d]">Copy these 3 things</p>
                        <p className="mt-2 text-sm leading-6 text-[#5f6470]">
                          Manual setup should be quick: install the SDK, add the env vars including
                          {` your Stimpact ${sdkCredentialLabel}, then paste the code into the detected entrypoint.`}
                        </p>
                        <div className="mt-4 grid gap-5">
                          {sdkManualPrimarySteps.map((item, index) => (
                            <div key={item.title} className="space-y-3">
                              <div className="flex items-start gap-3">
                                <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-[linear-gradient(180deg,#2d7ff9,#173fbe)] text-xs font-semibold text-white">
                                  {index + 1}
                                </span>
                                <div className="min-w-0">
                                  <p className="text-sm font-semibold text-[#171717]">{item.title}</p>
                                  <p className="mt-1 text-sm leading-6 text-[#5f6470]">{item.detail}</p>
                                </div>
                              </div>
                              <CodePanel title={item.title} code={item.code} />
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-[#171717]">After you paste the code</p>
                        <div className="mt-3 space-y-3">
                          {sdkManualFollowUpItems.map((item, index) => (
                            <div key={item} className="flex items-start gap-3">
                              <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[rgba(45,127,249,0.10)] text-[11px] font-semibold text-[#173fbe]">
                                {index + 1}
                              </span>
                              <p className="min-w-0 text-sm leading-6 text-[#5f6470]">{item}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      {sdkManualExtraNotes.length ? (
                        <div>
                          <p className="text-sm font-semibold text-[#17385d]">Need to know</p>
                          <div className="mt-3 space-y-2">
                            {sdkManualExtraNotes.map((item) => (
                              <p key={item} className="text-sm leading-6 text-[#315589]">
                                {item}
                              </p>
                            ))}
                          </div>
                          {sdkAttemptHistorySummary ? (
                            <p className="mt-3 text-sm leading-6 text-[#315589]">{sdkAttemptHistorySummary}</p>
                          ) : null}
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-sm text-[#746d66]">
                      Choose a repository and let the planner inspect it to generate setup guidance.
                    </p>
                  )}
                  <div className="flex flex-wrap gap-3">
                    <ActionButton
                      label="Mark manual setup complete"
                      onClick={() => {
                        setSdkSetupMode("manual");
                        void saveSdkSetupStatus("manual");
                      }}
                      disabled={loading || (!activeApiKeys.length && !activeBrowserKeys.length && !telemetryKeyPlaintext)}
                      variant="success"
                    />
                    {automaticSdkAvailable ? (
                      <ActionButton
                        label="Use automatic PR instead"
                        onClick={startAutomaticSdkWorkflow}
                        disabled={loading}
                        variant="secondary"
                      />
                    ) : null}
                  </div>
                </div>
              )}
            </div>

            <div className="border-t border-[rgba(17,24,39,0.08)] px-6 py-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-[#171717]">Heartbeat verification</p>
                  <p className="mt-1 max-w-3xl text-sm leading-6 text-[#746d66]">
                    This is the final check after setup and redeploy. Stimpact waits for a heartbeat
                    from the deployed SDK to confirm the service is live and ready to send telemetry.
                  </p>
                </div>
                <ActionButton
                  label="Refresh verification"
                  onClick={() => {
                    void loadTelemetryVerification();
                  }}
                  disabled={loading || loadingTelemetryVerification || !effectiveSdkServiceName.trim()}
                  variant="secondary"
                />
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${
                    telemetryVerification?.status === "healthy"
                      ? "bg-[linear-gradient(180deg,#22c55e,#16a34a)] text-white"
                      : telemetryVerification?.status === "stale"
                        ? "bg-[rgba(245,158,11,0.14)] text-[#9a5b14]"
                        : "bg-[rgba(29,26,24,0.08)] text-[#6f655d]"
                  }`}
                >
                  {telemetryVerificationStatusLabel}
                </span>
                <span className="text-xs text-[#8a8178]">
                  {effectiveSdkServiceName} / {sdkEnvironment.trim() || "production"}
                </span>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <StatusValueCard
                  label="Last heartbeat"
                  value={
                    telemetryVerification?.last_seen_at
                      ? formatHeartbeatTimestamp(telemetryVerification.last_seen_at)
                      : "Not seen yet"
                  }
                />
                <StatusValueCard
                  label="Last heartbeat commit"
                  value={telemetryVerification?.commit_sha ?? "Unavailable"}
                />
              </div>
              <p className="mt-4 text-sm leading-6 text-[#746d66]">
                {telemetryVerification?.status === "healthy"
                  ? "The deployed SDK is actively reaching Stimpact, so this service is live and ready to send telemetry when a real error occurs."
                  : telemetryVerification?.status === "stale"
                    ? "A heartbeat was seen before, but not recently. Redeploy the SDK-enabled service or refresh once the runtime is active again."
                    : "No heartbeat has been seen yet. Finish setup, redeploy the service, then refresh verification here."}
              </p>
            </div>
          </div>
        </StepPanel>

        <StepPanel
          step="07"
          stepKey="7"
          title="Review automation controls"
          description="Before the workspace is fully operational, confirm the autonomy mode and the core production safety guardrails for this project."
          complete={hasReviewedPolicy}
          editable={hasReviewedPolicy}
          isEditing={editingStepKey === "7"}
          editDisabled={Boolean(editingStepKey) && editingStepKey !== "7"}
          onEdit={() => beginStepEditing("7")}
          onCancelEdit={cancelStepEditing}
          sectionRef={(node) => {
            stepRefs.current["7"] = node;
          }}
        >
          {policyDraft ? (
            <div className="rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-[rgba(255,255,255,0.84)] p-5">
              <div className="grid gap-4 md:grid-cols-2">
                <SelectField
                  label="Autonomy mode"
                  value={policyDraft.autonomy_mode}
                  onChange={(value) =>
                    setPolicyDraft((current) =>
                      current
                        ? {
                            ...current,
                            autonomy_mode: value as ProjectPolicy["autonomy_mode"],
                          }
                        : current,
                    )
                  }
                  options={[
                    { value: "observe", label: "Observe" },
                    { value: "recommend", label: "Recommend" },
                    { value: "supervised_execute", label: "Supervised execute" },
                    { value: "autonomous", label: "Autonomous" },
                  ]}
                />
                <Field
                  label="Approved services"
                  value={policyDraft.approved_services.join(", ")}
                  onChange={(value) =>
                    setPolicyDraft((current) =>
                      current
                        ? {
                            ...current,
                            approved_services: value
                              .split(",")
                              .map((item) => item.trim())
                              .filter(Boolean),
                          }
                        : current,
                    )
                  }
                  placeholder="web-app, billing-api"
                  helperText="Only needed if you want autonomy restricted to a known subset of services."
                />
              </div>
              <div className="mt-5 grid gap-3">
                <PolicyToggleRow
                  label="Require human approval"
                  description="Keep an operator in the loop before Stimpact executes changes."
                  checked={policyDraft.require_human_approval}
                  onChange={(checked) =>
                    setPolicyDraft((current) =>
                      current ? { ...current, require_human_approval: checked } : current,
                    )
                  }
                />
                <PolicyToggleRow
                  label="Allow production writes"
                  description="Permit the platform to write back changes intended for production paths."
                  checked={policyDraft.allow_production_writes}
                  onChange={(checked) =>
                    setPolicyDraft((current) =>
                      current ? { ...current, allow_production_writes: checked } : current,
                    )
                  }
                />
                <PolicyToggleRow
                  label="Allow low-risk autonomy"
                  description="Let the platform handle lower-risk actions without escalating every time."
                  checked={policyDraft.allow_low_risk_autonomy}
                  onChange={(checked) =>
                    setPolicyDraft((current) =>
                      current ? { ...current, allow_low_risk_autonomy: checked } : current,
                    )
                  }
                />
                <PolicyToggleRow
                  label="Restrict to approved services"
                  description="Limit autonomy to the services listed above."
                  checked={policyDraft.restrict_to_approved_services}
                  onChange={(checked) =>
                    setPolicyDraft((current) =>
                      current ? { ...current, restrict_to_approved_services: checked } : current,
                    )
                  }
                />
              </div>
              <div className="mt-5">
                <ActionButton
                  label="Confirm automation controls"
                  onClick={saveAutomationControls}
                  disabled={loading}
                  variant="success"
                />
              </div>
            </div>
          ) : null}
        </StepPanel>

        <ManualFallbackDialog
          open={showSdkManualFallbackDialog}
          warnings={sdkBootstrapPlan?.warnings ?? []}
          strategy={selectedManualFallbackStrategy}
          onClose={() => setShowSdkManualFallbackDialog(false)}
          onConfirm={() => {
            openManualSdkMode();
          }}
        />
      </div>
    </div>
  );
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
  editable = false,
  isEditing = false,
  editDisabled = false,
  onEdit,
  onCancelEdit,
  sectionRef,
  children,
}: {
  step: string;
  stepKey: string;
  title: string;
  description: string;
  complete?: boolean;
  editable?: boolean;
  isEditing?: boolean;
  editDisabled?: boolean;
  onEdit?: () => void;
  onCancelEdit?: () => void;
  sectionRef?: (node: HTMLElement | null) => void;
  children: ReactNode;
}) {
  const sectionNodeRef = useRef<HTMLElement | null>(null);
  const locked = complete && editable && !isEditing;

  function handleSectionRef(node: HTMLElement | null) {
    sectionNodeRef.current = node;
    sectionRef?.(node);
  }

  function handleEdit() {
    onEdit?.();
    window.setTimeout(() => {
      focusEditableControl();
    }, 40);
  }

  function focusEditableControl() {
    const section = sectionNodeRef.current;
    if (!section) {
      return;
    }
    section.scrollIntoView({ behavior: "smooth", block: "start" });
    const target = section.querySelector<HTMLElement>(
      "input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href]",
    );
    window.setTimeout(() => {
      target?.focus();
    }, 180);
  }

  return (
    <section
      id={`onboarding-step-${stepKey}`}
      ref={handleSectionRef}
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
              {complete && editable && isEditing ? (
                <span className="inline-flex rounded-full bg-[rgba(255,106,61,0.12)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#9b4c2f]">
                  Editing
                </span>
              ) : null}
            </div>
            <h2 className="mt-3 text-2xl font-semibold text-[#171717]">{title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#5f6470]">{description}</p>
          </div>
          {complete && editable ? (
            isEditing ? (
              <button
                type="button"
                onClick={onCancelEdit}
                className="inline-flex items-center gap-2 self-start rounded-full border border-[rgba(29,26,24,0.08)] bg-white px-3 py-2 text-sm font-semibold text-[#5f6470] transition hover:border-[rgba(29,26,24,0.14)] hover:bg-[#faf7f4] hover:text-[#171717]"
              >
                Cancel
              </button>
            ) : (
              <button
                type="button"
                onClick={handleEdit}
                disabled={editDisabled}
                aria-label={`Edit step ${step}`}
                className="inline-flex h-11 w-11 cursor-pointer items-center justify-center self-start rounded-full border border-[rgba(23,56,93,0.14)] bg-white text-[#35547d] shadow-[0_10px_22px_rgba(15,23,42,0.08)] transition hover:-translate-y-0.5 hover:border-[rgba(255,106,61,0.24)] hover:bg-[#fff8f3] hover:text-[#171717] hover:shadow-[0_16px_30px_rgba(15,23,42,0.12)] disabled:cursor-not-allowed disabled:opacity-45"
              >
                <EditMiniGlyph />
              </button>
            )
          ) : null}
        </div>
        <div className={`mt-6 ${locked ? "pointer-events-none opacity-60 saturate-[0.92]" : ""}`}>{children}</div>
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
    <div className="mx-auto mt-8 max-w-[1320px]">
      <div className="relative hidden overflow-visible pb-2 pt-2 lg:block">
        <div
          className="absolute left-[10%] right-[10%] top-[3.75rem] h-[2px] bg-[linear-gradient(90deg,rgba(255,190,153,0.32),rgba(255,106,61,0.68),rgba(255,190,153,0.32))]"
        />
        <div className="grid grid-cols-7 gap-2">
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

function formatHeartbeatTimestamp(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return "Awaiting signal";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function PlusMiniGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4 fill-none stroke-current stroke-[1.8]">
      <path d="M8 3.25v9.5M3.25 8h9.5" strokeLinecap="round" />
    </svg>
  );
}

function CopyMiniGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4 fill-none stroke-current stroke-[1.6]">
      <rect x="6" y="4.5" width="6.5" height="8" rx="1.4" />
      <path
        d="M4.5 10.5H4A1.5 1.5 0 0 1 2.5 9V4A1.5 1.5 0 0 1 4 2.5h4A1.5 1.5 0 0 1 9.5 4v.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
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

function EditMiniGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4 fill-none stroke-current stroke-[1.6]">
      <path
        d="M10.95 2.55a1.55 1.55 0 0 1 2.19 0l.31.31a1.55 1.55 0 0 1 0 2.19l-7.2 7.2-2.8.62.62-2.8 6.88-6.88Z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M9.9 3.6 12.4 6.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RepoSecretMountEditor({
  mode,
  secretRefs,
  mounts,
  onAttachSecret,
  onUpdateMount,
  onRemoveMount,
}: {
  mode: "single" | "multi";
  secretRefs: ProjectOnboarding["secret_refs"];
  mounts: RepoSecretMountDraft[];
  onAttachSecret: (secretRefId: string) => void;
  onUpdateMount: (draftId: string, field: "secretRefId" | "mountAs", nextValue: string) => void;
  onRemoveMount: (draftId: string) => void;
}) {
  const attachedSecretIds = new Set(mounts.map((mount) => mount.secretRefId).filter(Boolean));
  const availableSecretRefs = secretRefs.filter((secretRef) => !attachedSecretIds.has(secretRef.id));
  const allProjectSecretsAttached = secretRefs.length > 0 && availableSecretRefs.length === 0;

  return (
    <div className="mt-4 border-t border-[rgba(17,24,39,0.08)] pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-[#171717]">Secret mounts</p>
          <p className="mt-1 text-sm leading-6 text-[#746d66]">
            {mode === "single"
              ? "For single repo setups, project secrets are auto-attached here so you can review and trim them instead of reselecting everything."
              : "Attach only the project secrets this repo actually needs, with one click from the list below."}
          </p>
        </div>
      </div>

      {secretRefs.length ? (
        <div className="mt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">
              {mode === "single" ? "Project secrets" : "Available project secrets"}
            </p>
            {mode === "single" && allProjectSecretsAttached ? (
              <p className="text-xs font-medium text-[#746d66]">
                All project secrets are attached. Remove any this repo does not need.
              </p>
            ) : null}
          </div>
          {availableSecretRefs.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {availableSecretRefs.map((secretRef) => (
                <button
                  key={secretRef.id}
                  type="button"
                  onClick={() => onAttachSecret(secretRef.id)}
                  className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-[rgba(17,24,39,0.08)] bg-white px-3 py-2 text-sm font-semibold text-[#17385d] transition hover:border-[rgba(255,106,61,0.22)] hover:bg-[#fff8f3] hover:text-[#171717]"
                >
                  <PlusMiniGlyph />
                  {secretRef.label}
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-[#746d66]">
              {mode === "single"
                ? "Everything from step 4 is already attached here for review."
                : "All available project secrets are already attached to this repo profile."}
            </p>
          )}
        </div>
      ) : null}

      {mounts.length ? (
        <div className="mt-4 overflow-hidden rounded-[18px] border border-[rgba(17,24,39,0.06)] bg-[rgba(255,255,255,0.82)]">
          <div className="border-b border-[rgba(17,24,39,0.06)] px-4 py-3">
            <p className="text-xs font-medium text-[#746d66]">
              Set the variable name or file path each attached secret should use inside the sandbox.
            </p>
          </div>
          {mounts.map((mount, index) => (
            <div
              key={mount.id}
              className={`px-4 py-4 ${index < mounts.length - 1 ? "border-b border-[rgba(17,24,39,0.06)]" : ""}`}
            >
              {(() => {
                const selectedSecret =
                  secretRefs.find((secretRef) => secretRef.id === mount.secretRefId) ?? null;
                return (
                  <div className="grid gap-3 md:grid-cols-[minmax(0,0.95fr)_minmax(0,1.1fr)_auto] md:items-end">
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8a8178]">
                        Secret {index + 1}
                      </p>
                      <p className="mt-1 truncate text-sm font-semibold text-[#171717]">
                        {selectedSecret?.label ?? "Unknown secret"}
                      </p>
                    </div>
                    <Field
                      label="Mount as"
                      value={mount.mountAs}
                      onChange={(value) => onUpdateMount(mount.id, "mountAs", value)}
                      placeholder="OPENAI_API_KEY or /var/run/..."
                    />
                    <div className="md:pb-[1px]">
                      <ActionButton
                        label="Remove"
                        onClick={() => onRemoveMount(mount.id)}
                        variant="secondary"
                      />
                    </div>
                  </div>
                );
              })()}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-[#746d66]">
          {mode === "single"
            ? "No secrets are attached yet. Add one from your project secret list only if this repo needs it to install or verify correctly."
            : "No secrets are attached yet. Pull in only the project secrets this repo needs."}
        </p>
      )}
    </div>
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
        <span className="font-semibold text-[#171717]">{label}</span>
        {helperText ? (
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-[#93867d]">{helperText}</span>
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
        className="w-full rounded-[16px] border border-[rgba(20,24,33,0.12)] bg-white px-4 py-3.5 text-sm text-[#171717] shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_1px_2px_rgba(15,23,42,0.04)] outline-none transition placeholder:text-[#a59b90] focus:border-[rgba(255,106,61,0.42)] focus:shadow-[0_0_0_4px_rgba(255,106,61,0.08),inset_0_1px_0_rgba(255,255,255,0.92)]"
      />
    </label>
  );
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[18px] border border-[rgba(17,24,39,0.08)] bg-[linear-gradient(180deg,rgba(247,242,236,0.96),rgba(239,232,223,0.96))] px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8a8178]">{label}</span>
        <span className="rounded-full bg-[rgba(29,26,24,0.08)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#6f655d]">
          Locked
        </span>
      </div>
      <div className="mt-3 text-sm font-medium text-[#171717]">{value}</div>
    </div>
  );
}

function StatusValueCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[18px] border border-[rgba(17,24,39,0.08)] bg-[linear-gradient(180deg,rgba(247,242,236,0.96),rgba(239,232,223,0.96))] px-4 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8a8178]">{label}</p>
      <p className="mt-3 text-base font-medium text-[#171717]">{value}</p>
    </div>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
  helperText,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  helperText?: string;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const selectedOption = options.find((option) => option.value === value) ?? options[0] ?? null;

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  return (
    <label className="block">
      <span className="mb-2 block text-sm font-semibold text-[#171717]">{label}</span>
      <div ref={containerRef} className="relative">
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          aria-haspopup="listbox"
          aria-expanded={open}
          className={`flex w-full items-center justify-between rounded-[16px] border px-4 py-3.5 text-left text-sm text-[#171717] shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_1px_2px_rgba(15,23,42,0.04)] outline-none transition ${
            open
              ? "border-[rgba(255,106,61,0.34)] bg-white shadow-[0_0_0_4px_rgba(255,106,61,0.08),0_18px_34px_rgba(15,23,42,0.08)]"
              : "border-[rgba(20,24,33,0.12)] bg-white hover:border-[rgba(255,106,61,0.2)] hover:shadow-[0_10px_20px_rgba(15,23,42,0.06)]"
          }`}
        >
          <span>{selectedOption?.label ?? "Select an option"}</span>
          <span
            aria-hidden="true"
            className={`ml-3 text-[#8a8178] transition ${open ? "rotate-180" : ""}`}
          >
            <svg
              viewBox="0 0 20 20"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m5.5 7.75 4.5 4.5 4.5-4.5" />
            </svg>
          </span>
        </button>

        {open ? (
          <div
            role="listbox"
            className="absolute left-0 right-0 top-[calc(100%+0.55rem)] z-30 max-h-[280px] overflow-y-auto rounded-[20px] border border-[rgba(29,26,24,0.10)] bg-[linear-gradient(180deg,rgba(255,250,245,0.98),rgba(249,241,232,0.98))] p-2 shadow-[0_24px_48px_rgba(15,23,42,0.16)] backdrop-blur-xl"
          >
            {options.map((option) => {
              const active = option.value === value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center justify-between rounded-[14px] px-3 py-3 text-sm transition ${
                    active
                      ? "bg-[rgba(255,106,61,0.14)] text-[#171717]"
                      : "text-[#5f6470] hover:bg-[rgba(255,255,255,0.82)] hover:text-[#171717]"
                  }`}
                >
                  <span>{option.label}</span>
                  {active ? (
                    <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#9b4c2f]">
                      Selected
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
      {helperText ? <p className="mt-2 text-[12px] leading-5 text-[#93867d]">{helperText}</p> : null}
    </label>
  );
}

function CodePanel({ title, code }: { title: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const lines = code.split("\n");

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => {
        setCopied(false);
      }, 1800);
    } catch {
      // Ignore clipboard failures and leave the code visible for manual copy.
    }
  }

  const lineToneClass = (line: string) => {
    if (line.startsWith("+") && !line.startsWith("+++")) {
      return "text-[#86efac]";
    }
    if (line.startsWith("-") && !line.startsWith("---")) {
      return "text-[#fca5a5]";
    }
    if (line.startsWith("@@")) {
      return "text-[#93c5fd]";
    }
    if (line.trim().startsWith("#") || line.trim().startsWith("//")) {
      return "text-[#94a3b8]";
    }
    if (/^[A-Z0-9_]+=/.test(line)) {
      return "text-[#f8c26a]";
    }
    return "text-[#e5eefc]";
  };

  return (
    <div className="overflow-hidden rounded-[20px] border border-[rgba(15,23,42,0.18)] bg-[#0b1220] shadow-[0_18px_38px_rgba(15,23,42,0.14)]">
      <div className="flex items-center justify-between border-b border-[rgba(148,163,184,0.18)] bg-[rgba(15,23,42,0.88)] px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#fb7185]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#fbbf24]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#34d399]" />
          </div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#c4d3ea]">{title}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-medium text-[#7f91ab]">{lines.length} lines</span>
          <button
            type="button"
            onClick={() => {
              void copyCode();
            }}
            className="rounded-full border border-[rgba(148,163,184,0.18)] px-3 py-1 text-[11px] font-semibold text-[#d8e4f8] transition hover:border-[rgba(96,165,250,0.34)] hover:bg-[rgba(30,41,59,0.82)]"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <pre className="min-w-full bg-[#0b1220] py-3 text-xs leading-6">
          <code>
            {lines.map((line, index) => (
              <div key={`${title}-${index}`} className="grid grid-cols-[3.5rem_minmax(0,1fr)]">
                <span className="select-none border-r border-[rgba(148,163,184,0.10)] px-3 text-right text-[#5f6f86]">
                  {index + 1}
                </span>
                <span className={`whitespace-pre px-4 ${lineToneClass(line)}`}>{line || " "}</span>
              </div>
            ))}
          </code>
        </pre>
      </div>
    </div>
  );
}

function DiffReviewPanel({
  title,
  files,
  plannedFiles,
  rawDiff,
}: {
  title: string;
  files: ParsedDiffFile[];
  plannedFiles: SdkBootstrapPreview["strategy"]["planned_files"];
  rawDiff: string | null;
}) {
  const plannedFileMap = new Map(plannedFiles.map((item) => [item.path, item]));

  if (!files.length) {
    return <CodePanel title={title} code={rawDiff ?? "# Patch preview is unavailable for this attempt"} />;
  }

  return (
    <div className="overflow-hidden rounded-[22px] border border-[rgba(15,23,42,0.18)] bg-[#0b1220] shadow-[0_18px_38px_rgba(15,23,42,0.14)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[rgba(148,163,184,0.18)] bg-[rgba(15,23,42,0.88)] px-5 py-4">
        <div>
          <p className="text-sm font-semibold text-white">{title}</p>
          <p className="mt-1 text-sm text-[#8ea2bf]">
            Review each file below. Added lines are green, removed lines are red.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full bg-[rgba(45,127,249,0.16)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#c9ddff]">
            {files.length} files
          </span>
          <span className="rounded-full bg-[rgba(34,197,94,0.16)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#bbf7d0]">
            +{files.reduce((total, file) => total + file.additions, 0)}
          </span>
          <span className="rounded-full bg-[rgba(248,113,113,0.16)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#fecaca]">
            -{files.reduce((total, file) => total + file.deletions, 0)}
          </span>
        </div>
      </div>

      <div className="divide-y divide-[rgba(148,163,184,0.14)]">
        {files.map((file) => {
          const plannedFile = plannedFileMap.get(file.path);
          return (
            <div key={`${file.previousPath ?? "new"}-${file.path}`} className="bg-[#0b1220]">
              <div className="flex flex-wrap items-start justify-between gap-3 bg-[rgba(15,23,42,0.72)] px-5 py-4">
                <div className="min-w-0">
                  <p className="truncate font-mono text-sm text-[#f8fafc]">{file.path}</p>
                  {plannedFile?.reason ? (
                    <p className="mt-1 text-sm leading-6 text-[#8ea2bf]">{plannedFile.reason}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {plannedFile?.action ? (
                    <span className="rounded-full bg-[rgba(45,127,249,0.16)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#c9ddff]">
                      {plannedFile.action}
                    </span>
                  ) : null}
                  <span className="rounded-full bg-[rgba(34,197,94,0.16)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#bbf7d0]">
                    +{file.additions}
                  </span>
                  <span className="rounded-full bg-[rgba(248,113,113,0.16)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#fecaca]">
                    -{file.deletions}
                  </span>
                </div>
              </div>
              <div className="max-h-[420px] overflow-auto">
                {file.lines.map((line, index) => (
                  <div
                    key={`${file.path}-${index}`}
                    className={`grid grid-cols-[4.25rem_4.25rem_minmax(0,1fr)] text-xs leading-6 ${
                      line.kind === "add"
                        ? "bg-[rgba(34,197,94,0.12)]"
                        : line.kind === "remove"
                          ? "bg-[rgba(248,113,113,0.12)]"
                          : line.kind === "meta"
                            ? "bg-[rgba(59,130,246,0.12)]"
                            : "bg-transparent"
                    }`}
                  >
                    <span className="select-none border-r border-[rgba(148,163,184,0.10)] px-3 text-right text-[#5f6f86]">
                      {line.oldLineNumber ?? ""}
                    </span>
                    <span className="select-none border-r border-[rgba(148,163,184,0.10)] px-3 text-right text-[#5f6f86]">
                      {line.newLineNumber ?? ""}
                    </span>
                    <span
                      className={`whitespace-pre px-4 font-mono ${
                        line.kind === "add"
                          ? "text-[#bbf7d0]"
                          : line.kind === "remove"
                            ? "text-[#fecaca]"
                            : line.kind === "meta"
                              ? "text-[#bfdbfe]"
                              : "text-[#e5eefc]"
                      }`}
                    >
                      {line.content || " "}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PolicyToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 rounded-[18px] border border-[rgba(17,24,39,0.08)] bg-white px-4 py-4">
      <div>
        <p className="text-sm font-semibold text-[#171717]">{label}</p>
        <p className="mt-1 text-sm leading-6 text-[#746d66]">{description}</p>
      </div>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`inline-flex h-7 min-w-[3.25rem] items-center rounded-full border px-1 transition ${
          checked
            ? "border-[rgba(22,163,74,0.28)] bg-[linear-gradient(180deg,#22c55e,#16a34a)] justify-end"
            : "border-[rgba(17,24,39,0.1)] bg-[rgba(29,26,24,0.08)] justify-start"
        }`}
        aria-pressed={checked}
      >
        <span className="h-5 w-5 rounded-full bg-white shadow-[0_4px_10px_rgba(15,23,42,0.12)]" />
      </button>
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
      className={`inline-flex items-center justify-center rounded-full px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${
        variant === "secondary"
          ? "border border-[rgba(23,56,93,0.14)] bg-white text-[#17385d] shadow-[0_10px_24px_rgba(15,23,42,0.06)] hover:-translate-y-0.5 hover:border-[rgba(255,106,61,0.24)] hover:shadow-[0_14px_28px_rgba(15,23,42,0.10)]"
          : variant === "success"
            ? "bg-[linear-gradient(180deg,#1fbf68_0%,#16a34a_100%)] text-white shadow-[0_14px_28px_rgba(22,163,74,0.18)] hover:-translate-y-0.5 hover:shadow-[0_18px_34px_rgba(22,163,74,0.24)]"
          : "bg-[linear-gradient(180deg,#ff754b_0%,#ff5a2a_100%)] text-white shadow-[0_14px_28px_rgba(255,106,61,0.2)] hover:-translate-y-0.5 hover:shadow-[0_18px_34px_rgba(255,106,61,0.26)]"
      }`}
    >
      {label}
    </button>
  );
}

function ManualFallbackDialog({
  open,
  warnings,
  strategy,
  onClose,
  onConfirm,
}: {
  open: boolean;
  warnings: string[];
  strategy: SdkBootstrapPlanPreview["strategies"][number] | null;
  onClose: () => void;
  onConfirm: () => void;
}) {
  if (!open || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-[rgba(15,23,42,0.42)] px-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-[28px] border border-[rgba(29,26,24,0.08)] bg-[linear-gradient(180deg,#fffdfb,#f8efe7)] p-6 shadow-[0_28px_80px_rgba(15,23,42,0.22)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9b4c2f]">
              Automatic setup unavailable
            </p>
            <h3 className="mt-2 text-xl font-semibold text-[#171717]">
              Stimpact could not prepare a safe automatic SDK PR
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-[rgba(29,26,24,0.08)] bg-white/80 px-3 py-1.5 text-xs font-semibold text-[#6f655d] transition hover:border-[rgba(255,106,61,0.2)] hover:bg-white"
          >
            Close
          </button>
        </div>

        <p className="mt-4 text-sm leading-6 text-[#746d66]">
          The planner inspected this repository, but it did not find a safe runtime entrypoint for an
          automatic patch. Stimpact kept the safer manual route instead of guessing.
        </p>

        {warnings.length ? (
          <div className="mt-4 space-y-2">
            {warnings.map((warning) => (
              <p
                key={warning}
                className="rounded-[16px] bg-[rgba(255,106,61,0.08)] px-4 py-3 text-sm text-[#8f4b31]"
              >
                {warning}
              </p>
            ))}
          </div>
        ) : null}

        {strategy ? (
          <div className="mt-4 rounded-[18px] border border-[rgba(17,24,39,0.08)] bg-white/80 px-4 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-[#171717]">{strategy.framework}</p>
              <span className="rounded-full bg-[rgba(29,26,24,0.08)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#6f655d]">
                Manual setup
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-[#746d66]">{strategy.summary}</p>
            {strategy.blockers.length ? (
              <ul className="mt-3 grid gap-2 text-sm text-[#5f6470]">
                {strategy.blockers.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap gap-3">
          <ActionButton label="Continue to manual setup" onClick={onConfirm} />
          <ActionButton label="Stay here" onClick={onClose} variant="secondary" />
        </div>
      </div>
    </div>,
    document.body,
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
