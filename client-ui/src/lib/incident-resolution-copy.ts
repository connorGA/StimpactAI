import type {
  AutonomousApprovalStatus,
  AutonomousExecutionMode,
  AutonomousRunPhase,
  AutonomousRunStatus,
} from "@/lib/types";

const PHASE_LABEL: Record<AutonomousRunPhase, string> = {
  initializer: "Initializing workspace",
  coding: "Analyzing and applying changes",
  verification: "Verifying fix",
  recovery: "Recovering from errors",
  /** Internal run state: agent loop ended — not the same as “incident resolved”. */
  completed: "Run finished",
  failed: "Run failed (phase)",
};

const MODE_LABEL: Record<AutonomousExecutionMode, string> = {
  investigate_only: "Investigate",
  repair_only: "Repair",
  repair_and_propose: "Repair + PR/MR",
};

export function formatAutonomousPhase(phase: AutonomousRunPhase): string {
  return PHASE_LABEL[phase] ?? phase;
}

export function formatAutonomousExecutionMode(mode: AutonomousExecutionMode): string {
  return MODE_LABEL[mode] ?? mode;
}

export function formatAutonomousApprovalStatus(status: AutonomousApprovalStatus): string {
  switch (status) {
    case "not_required":
      return "Not required";
    case "pending":
      return "Awaiting your approval";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    default:
      return status;
  }
}

/** One-line headline for the live resolution strip on incident detail. */
export function autonomousResolutionHeadline(input: {
  status: AutonomousRunStatus;
  phase: AutonomousRunPhase;
  approval_status: AutonomousApprovalStatus;
  execution_mode: AutonomousExecutionMode;
}): string {
  if (input.approval_status === "pending") {
    return "Waiting on manual approval before the agent can continue.";
  }
  if (input.status === "queued") {
    return `${formatAutonomousExecutionMode(input.execution_mode)} run is queued.`;
  }
  if (input.status === "running") {
    return `${formatAutonomousPhase(input.phase)} · ${formatAutonomousExecutionMode(input.execution_mode)}`;
  }
  if (input.status === "succeeded") {
    return "Autonomous run finished successfully.";
  }
  if (input.status === "failed") {
    return "Autonomous run ended with an error.";
  }
  if (input.status === "cancelled") {
    return "Autonomous run was cancelled.";
  }
  return "Autonomous resolution";
}
