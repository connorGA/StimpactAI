import type {
  ProjectSdkSetupState,
  ProjectTelemetryVerification,
} from "@/lib/types";

export function getStepSixCompletion(stepSix: ProjectSdkSetupState | null): boolean {
  return stepSix?.complete ?? false;
}

export function getSdkSetupStatusLabel(stepSix: ProjectSdkSetupState | null): string {
  if (!stepSix) {
    return "Pending";
  }
  if (stepSix.integration_mode === "change_request") {
    return "Bootstrap PR opened";
  }
  if (stepSix.integration_mode === "manual" && stepSix.analysis_status === "ready") {
    return "Manual setup ready";
  }
  if (stepSix.integration_mode === "patch_bundle") {
    return "Patch bundle ready";
  }
  return "Pending";
}

export function getTelemetryVerificationStatusLabel(
  verification: ProjectTelemetryVerification | null,
  stepSix: ProjectSdkSetupState | null,
  loading: boolean,
): string {
  const status = verification?.status ?? stepSix?.verification?.status ?? null;
  if (status === "healthy") {
    return "Live heartbeat detected";
  }
  if (status === "stale") {
    return "Heartbeat stale";
  }
  if (status === "mismatched_target") {
    return "Heartbeat target mismatch";
  }
  if (loading) {
    return "Checking heartbeat";
  }
  return "Waiting for first heartbeat";
}

export function getTelemetryVerificationCopy(
  verification: ProjectTelemetryVerification | null,
  stepSix: ProjectSdkSetupState | null,
): string {
  const effective = verification ?? stepSix?.verification ?? null;
  if (effective?.status === "healthy") {
    return "The deployed SDK is actively reaching Stimpact, so this service is live and ready to send telemetry when a real error occurs.";
  }
  if (effective?.status === "stale") {
    return "A heartbeat was seen before, but not recently. Redeploy the SDK-enabled service or refresh once the runtime is active again.";
  }
  if (effective?.status === "mismatched_target") {
    return "Telemetry is reaching Stimpact, but not from the exact service and environment selected for this setup. Align the generated service or environment values with the deployed app and check again.";
  }
  return "No heartbeat has been seen yet. Finish setup, redeploy the service, then refresh verification here.";
}
