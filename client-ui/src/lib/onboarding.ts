import type { ProjectOnboarding } from "@/lib/types";

export type ProjectOnboardingProgress = {
  hasProviderConnection: boolean;
  hasSyncedRepositories: boolean;
  hasSecrets: boolean;
  hasRepoProfiles: boolean;
  hasServices: boolean;
};

export function getProjectOnboardingProgress(
  onboarding: Pick<
    ProjectOnboarding,
    "integrations" | "secret_refs" | "repo_profiles" | "project_services"
  >,
): ProjectOnboardingProgress {
  return {
    hasProviderConnection: onboarding.integrations.length > 0,
    hasSyncedRepositories: onboarding.integrations.some(
      (integration) => integration.repositories.length > 0,
    ),
    hasSecrets: onboarding.secret_refs.length > 0,
    hasRepoProfiles: onboarding.repo_profiles.length > 0,
    hasServices: onboarding.project_services.length > 0,
  };
}

export function isProjectOnboardingComplete(
  onboarding: Pick<
    ProjectOnboarding,
    "integrations" | "secret_refs" | "repo_profiles" | "project_services"
  >,
): boolean {
  const progress = getProjectOnboardingProgress(onboarding);
  return (
    progress.hasProviderConnection &&
    progress.hasSyncedRepositories &&
    progress.hasSecrets &&
    progress.hasRepoProfiles &&
    progress.hasServices
  );
}
