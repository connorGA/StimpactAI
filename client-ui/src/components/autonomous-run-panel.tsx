"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  AutonomousApprovalStatus,
  AutonomousExecutionMode,
  IncidentAutonomousRunDetail,
} from "@/lib/types";
import { formatTimestamp } from "@/lib/dashboard";

type AutonomousRunPanelProps = {
  incidentId: string;
  initialDetail: IncidentAutonomousRunDetail | null;
};

export function AutonomousRunPanel({
  incidentId,
  initialDetail,
}: AutonomousRunPanelProps) {
  const [detail, setDetail] = useState<IncidentAutonomousRunDetail | null>(initialDetail);
  const [connectionState, setConnectionState] = useState<"live" | "reconnecting">(
    "live",
  );
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const activeRunId = detail?.run.id ?? null;
  const isActiveRun =
    detail?.run.status === "running" || detail?.run.status === "queued";
  const streamState = !isActiveRun ? "idle" : connectionState;

  const refreshLatestDetail = useCallback(async () => {
    const response = await fetch(
      `/api/incidents/${incidentId}/autonomous-runs/latest`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      throw new Error("Failed to load the latest autonomous run.");
    }
    const latest = (await response.json()) as IncidentAutonomousRunDetail;
    setDetail(latest);
    return latest;
  }, [incidentId]);

  async function runJsonAction<T>(
    path: string,
    options?: RequestInit,
  ): Promise<T> {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options?.headers ?? {}),
      },
    });
    if (!response.ok) {
      let message = "Autonomous action failed.";
      try {
        const payload = (await response.json()) as { error?: { message?: string } };
        if (payload.error?.message) {
          message = payload.error.message;
        }
      } catch {
        // Keep the default fallback message.
      }
      throw new Error(message);
    }
    return (await response.json()) as T;
  }

  async function startRun(executionMode: AutonomousExecutionMode) {
    setActionError(null);
    setActiveAction(`start:${executionMode}`);
    try {
      await runJsonAction(
        `/api/incidents/${incidentId}/autonomous-runs`,
        {
          method: "POST",
          body: JSON.stringify({
            execution_mode: executionMode,
            allow_writeback: executionMode === "repair_and_propose",
            require_human_approval: executionMode === "repair_and_propose",
          }),
        },
      );
      await refreshLatestDetail();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to start autonomous run.");
    } finally {
      setActiveAction(null);
    }
  }

  async function setApprovalStatus(approvalStatus: AutonomousApprovalStatus) {
    if (!detail) {
      return;
    }
    setActionError(null);
    setActiveAction(`approval:${approvalStatus}`);
    try {
      const next = await runJsonAction<IncidentAutonomousRunDetail>(
        `/api/incidents/${incidentId}/autonomous-runs/${detail.run.id}/approval`,
        {
          method: "POST",
          body: JSON.stringify({ approval_status: approvalStatus }),
        },
      );
      setDetail(next);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to update approval state.");
    } finally {
      setActiveAction(null);
    }
  }

  async function promoteRun() {
    if (!detail) {
      return;
    }
    setActionError(null);
    setActiveAction("promote");
    try {
      const next = await runJsonAction<IncidentAutonomousRunDetail>(
        `/api/incidents/${incidentId}/autonomous-runs/${detail.run.id}/promote`,
        { method: "POST" },
      );
      setDetail(next);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to promote autonomous run.");
    } finally {
      setActiveAction(null);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function refreshLatest() {
      try {
        await refreshLatestDetail();
        if (cancelled) {
          return;
        }
      } catch {
        // Keep the previous detail when the poll fails.
      }
    }

    if (isActiveRun) {
      return () => {
        cancelled = true;
      };
    }

    void refreshLatest();
    const interval = window.setInterval(() => {
      void refreshLatest();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [incidentId, isActiveRun, refreshLatestDetail]);

  useEffect(() => {
    if (!activeRunId || !isActiveRun) {
      return;
    }

    const source = new EventSource(
      `/api/incidents/${incidentId}/autonomous-runs/${activeRunId}/events`,
    );

    source.onopen = () => {
      setConnectionState("live");
    };

    source.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data) as IncidentAutonomousRunDetail;
        setDetail(next);
        setConnectionState(
          next.run.status === "running" || next.run.status === "queued"
            ? "live"
            : "live",
        );
        if (
          next.run.status === "succeeded" ||
          next.run.status === "failed" ||
          next.run.status === "cancelled"
        ) {
          source.close();
        }
      } catch {
        setConnectionState("reconnecting");
      }
    };

    source.onerror = () => {
      setConnectionState("reconnecting");
      source.close();
    };

    return () => {
      source.close();
    };
  }, [activeRunId, incidentId, isActiveRun]);

  const recentEvents = useMemo(
    () => (detail?.events ?? []).slice(-12).reverse(),
    [detail],
  );

  const canRetry =
    detail?.run.status === "failed" ||
    detail?.run.status === "cancelled" ||
    detail?.run.status === "succeeded";

  return (
    <section className="ops-sheet rounded-[22px] p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="ops-kicker text-[11px] font-semibold uppercase">
            Autonomous repair run
          </p>
          <h3 className="mt-3 text-base font-semibold text-[#171717]">
            {detail ? detail.run.objective : "No autonomous repair runs yet"}
          </h3>
        </div>
        {detail ? (
          <div className="flex flex-col items-end gap-2">
            <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#745744]">
              {detail.run.status}
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#6380a3]">
              {streamState === "live"
                ? "Live"
                : streamState === "reconnecting"
                  ? "Reconnecting"
                  : "Snapshot"}
            </span>
          </div>
        ) : null}
      </div>

      {detail ? (
        <>
          <div className="mt-4 grid gap-4">
            <AutonomousMetaRow label="Phase" value={detail.run.phase} />
            <AutonomousMetaRow label="Mode" value={detail.run.execution_mode} />
            <AutonomousMetaRow
              label="Approval"
              value={detail.run.approval_status}
            />
            <AutonomousMetaRow
              label="Promotion"
              value={detail.run.promotion_status}
            />
            <AutonomousMetaRow
              label="Progress"
              value={`${detail.run.loop_state.step_index}/${detail.run.loop_state.max_steps} steps`}
            />
            <AutonomousMetaRow
              label="Recovery attempts"
              value={String(detail.run.loop_state.recovery_attempts)}
            />
            <AutonomousMetaRow
              label="Last tool"
              value={detail.run.loop_state.last_tool_name ?? "No tool has run yet"}
            />
            <AutonomousMetaRow
              label="Checkpoint"
              value={detail.run.loop_state.checkpoint_ref ?? "No checkpoint yet"}
            />
          </div>

          <div className="mt-5 rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
              Operator controls
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <ActionButton
                label="Investigate only"
                disabled={activeAction !== null}
                active={activeAction === "start:investigate_only"}
                onClick={() => startRun("investigate_only")}
              />
              <ActionButton
                label="Repair only"
                disabled={activeAction !== null}
                active={activeAction === "start:repair_only"}
                onClick={() => startRun("repair_only")}
              />
              <ActionButton
                label="Repair + PR/MR"
                disabled={activeAction !== null}
                active={activeAction === "start:repair_and_propose"}
                onClick={() => startRun("repair_and_propose")}
              />
              {detail.run.approval_status === "pending" ? (
                <>
                  <ActionButton
                    label="Approve"
                    disabled={activeAction !== null}
                    active={activeAction === "approval:approved"}
                    onClick={() => setApprovalStatus("approved")}
                  />
                  <ActionButton
                    label="Reject"
                    disabled={activeAction !== null}
                    active={activeAction === "approval:rejected"}
                    onClick={() => setApprovalStatus("rejected")}
                  />
                </>
              ) : null}
              {detail.run.promotion_status === "ready" ? (
                <ActionButton
                  label="Promote"
                  disabled={activeAction !== null}
                  active={activeAction === "promote"}
                  onClick={promoteRun}
                />
              ) : null}
              {canRetry ? (
                <ActionButton
                  label="Retry"
                  disabled={activeAction !== null}
                  active={false}
                  onClick={() => startRun(detail.run.execution_mode)}
                />
              ) : null}
            </div>
            {actionError ? (
              <p className="mt-3 text-sm text-[#b4453d]">{actionError}</p>
            ) : null}
          </div>

          <div className="mt-5 rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
              Policy and readiness
            </p>
            <div className="mt-3 grid gap-3 text-sm text-[#5f6470]">
              <AutonomousMetaRow
                label="Auto-run allowed"
                value={detail.run.policy.auto_run_allowed ? "Yes" : "No"}
              />
              <AutonomousMetaRow
                label="Write-back allowed"
                value={detail.run.policy.allow_writeback ? "Yes" : "No"}
              />
              <AutonomousMetaRow
                label="Browser verification required"
                value={detail.run.policy.require_browser_verification ? "Yes" : "No"}
              />
              <AutonomousMetaRow
                label="Allowed backends"
                value={detail.run.policy.allowed_execution_backends.join(", ") || "None"}
              />
              <AutonomousMetaRow
                label="Allowed tools"
                value={detail.run.policy.allowed_tool_categories.join(", ") || "None"}
              />
              <AutonomousMetaRow
                label="Repo profile"
                value={detail.run.repo_profile_id ?? "Not resolved"}
              />
              <AutonomousMetaRow
                label="Patch run"
                value={detail.run.patch_run_id ?? "Pending"}
              />
              <AutonomousMetaRow
                label="Sandbox run"
                value={detail.run.sandbox_run_id ?? "Pending"}
              />
            </div>
            {detail.run.policy.reasons.length > 0 ? (
              <div className="mt-3 rounded-2xl bg-[rgba(244,248,253,0.85)] p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                  Policy reasons
                </p>
                <div className="mt-2 space-y-2 text-sm text-[#5f6470]">
                  {detail.run.policy.reasons.map((reason) => (
                    <p key={reason}>{reason}</p>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          {detail.outcome ? (
            <div className="mt-5 rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                Outcome record
              </p>
              <div className="mt-3 grid gap-3 text-sm text-[#5f6470]">
                <AutonomousMetaRow
                  label="Decisions"
                  value={String(detail.outcome.total_decisions)}
                />
                <AutonomousMetaRow
                  label="Tool calls"
                  value={String(detail.outcome.total_tool_calls)}
                />
                <AutonomousMetaRow
                  label="Completed"
                  value={formatTimestamp(detail.outcome.completed_at)}
                />
                <AutonomousMetaRow
                  label="Approval"
                  value={detail.outcome.approval_status}
                />
                <AutonomousMetaRow
                  label="Promotion"
                  value={detail.outcome.promotion_status}
                />
              </div>
            </div>
          ) : null}

          <div className="mt-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
              Live event timeline
            </p>
            <div className="mt-3 max-h-96 space-y-3 overflow-auto pr-1">
              {recentEvents.map((event) => (
                <div
                  key={event.id}
                  className="rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 px-4 py-4"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-[#17385d]">
                        {event.summary}
                      </p>
                      <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                        {event.event_type} • {event.phase}
                      </p>
                    </div>
                    <span className="text-xs text-[#667085]">
                      {formatTimestamp(event.created_at)}
                    </span>
                  </div>
                  {event.decision?.selected_tool ? (
                    <p className="mt-2 text-sm text-[#5f6470]">
                      Tool: {event.decision.selected_tool}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </div>

          <div className="mt-5 rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
              Durable artifacts
            </p>
            <div className="mt-3 grid gap-3 text-sm text-[#5f6470]">
              <AutonomousMetaRow
                label="Snapshot"
                value={detail.artifact_paths.snapshot_path}
              />
              <AutonomousMetaRow
                label="Transcript"
                value={detail.artifact_paths.events_path}
              />
              <AutonomousMetaRow
                label="Outcome"
                value={detail.artifact_paths.outcome_path ?? "Pending"}
              />
              <AutonomousMetaRow
                label="Promotion URL"
                value={detail.run.promotion_url ?? "Pending"}
              />
            </div>
          </div>

          {detail.run.last_error ? (
            <div className="mt-5 rounded-2xl border border-[rgba(233,89,80,0.18)] bg-[rgba(255,245,244,0.9)] p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#b4453d]">
                Last error
              </p>
              <p className="mt-2 text-sm leading-6 text-[#8b433c]">
                {detail.run.last_error}
              </p>
            </div>
          ) : null}
        </>
      ) : (
        <div className="mt-4 space-y-4">
          <p className="text-sm leading-6 text-[#746d66]">
            No autonomous repair run has been persisted for this incident yet.
            Launch one of the regulated run modes below to begin.
          </p>
          <div className="flex flex-wrap gap-2">
            <ActionButton
              label="Investigate only"
              disabled={activeAction !== null}
              active={activeAction === "start:investigate_only"}
              onClick={() => startRun("investigate_only")}
            />
            <ActionButton
              label="Repair only"
              disabled={activeAction !== null}
              active={activeAction === "start:repair_only"}
              onClick={() => startRun("repair_only")}
            />
            <ActionButton
              label="Repair + PR/MR"
              disabled={activeAction !== null}
              active={activeAction === "start:repair_and_propose"}
              onClick={() => startRun("repair_and_propose")}
            />
          </div>
          {actionError ? (
            <p className="text-sm text-[#b4453d]">{actionError}</p>
          ) : null}
        </div>
      )}
    </section>
  );
}

function AutonomousMetaRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[rgba(24,24,27,0.08)] py-2 last:border-b-0">
      <span className="text-sm text-[#667085]">{label}</span>
      <span className="break-all text-right text-sm font-semibold text-[#111827]">
        {value}
      </span>
    </div>
  );
}

function ActionButton({
  label,
  disabled,
  active,
  onClick,
}: {
  label: string;
  disabled: boolean;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${
        active
          ? "bg-[#17385d] text-white"
          : "bg-[#f4f8fd] text-[#35547d] hover:bg-[#e6eef8]"
      } disabled:cursor-not-allowed disabled:opacity-60`}
    >
      {active ? "Working..." : label}
    </button>
  );
}
