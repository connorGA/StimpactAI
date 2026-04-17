import type {
  ProjectTelemetryVerification,
} from "@/lib/types";

type LegacyProjectSdkSetupState = {
  complete?: boolean;
  integration_mode?: "change_request" | "manual" | "patch_bundle" | string | null;
  analysis_status?: "ready" | string | null;
  verification?: ProjectTelemetryVerification | null;
};

export function getStepSixCompletion(stepSix: LegacyProjectSdkSetupState | null): boolean {
  return stepSix?.complete ?? false;
}

export function getSdkSetupStatusLabel(stepSix: LegacyProjectSdkSetupState | null): string {
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
  stepSix: LegacyProjectSdkSetupState | null,
  loading: boolean,
): string {
  const status = (verification?.status ?? stepSix?.verification?.status ?? null) as string | null;
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
  stepSix: LegacyProjectSdkSetupState | null,
): string {
  const effective = verification ?? stepSix?.verification ?? null;
  const effectiveStatus = effective?.status as string | null;
  if (effectiveStatus === "healthy") {
    return "The deployed SDK is actively reaching Stimpact, so this service is live and ready to send telemetry when a real error occurs.";
  }
  if (effectiveStatus === "stale") {
    return "A heartbeat was seen before, but not recently. Redeploy the SDK-enabled service or refresh once the runtime is active again.";
  }
  if (effectiveStatus === "mismatched_target") {
    return "Telemetry is reaching Stimpact, but not from the exact service and environment selected for this setup. Align the generated service or environment values with the deployed app and check again.";
  }
  return "No heartbeat has been seen yet. Finish setup, redeploy the service, then refresh verification here.";
}
