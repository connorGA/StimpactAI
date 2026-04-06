import type { ProjectOnboarding } from "@/lib/types";

export type ProjectOnboardingProgress = {
  hasProviderConnection: boolean;
  hasSyncedRepositories: boolean;
  hasSecrets: boolean;
  hasRepoProfiles: boolean;
  hasServices: boolean;
  hasActiveApiKeys: boolean;
  hasReviewedPolicy: boolean;
  hasSdkSetup: boolean;
};

export function getProjectOnboardingProgress(
  onboarding: Pick<
    ProjectOnboarding,
    | "integrations"
    | "secret_refs"
    | "repo_profiles"
    | "project_services"
    | "api_keys"
    | "onboarding_state"
    | "operational_readiness"
  >,
): ProjectOnboardingProgress {
  return {
    hasProviderConnection: onboarding.operational_readiness.has_provider_connection,
    hasSyncedRepositories: onboarding.operational_readiness.has_synced_repositories,
    hasSecrets: onboarding.operational_readiness.has_secrets,
    hasRepoProfiles: onboarding.operational_readiness.has_repo_profiles,
    hasServices: onboarding.operational_readiness.has_services,
    hasActiveApiKeys:
      onboarding.operational_readiness.has_active_api_keys ||
      onboarding.operational_readiness.has_active_browser_keys,
    hasReviewedPolicy: onboarding.operational_readiness.policy_reviewed,
    hasSdkSetup: onboarding.operational_readiness.sdk_setup_ready,
  };
}

export function isProjectOnboardingComplete(
  onboarding: Pick<
    ProjectOnboarding,
    | "integrations"
    | "secret_refs"
    | "repo_profiles"
    | "project_services"
    | "api_keys"
    | "onboarding_state"
    | "operational_readiness"
  >,
): boolean {
  return onboarding.operational_readiness.complete;
}
