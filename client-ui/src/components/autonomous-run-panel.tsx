"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { formatTimestamp } from "@/lib/dashboard";
import {
  autonomousResolutionHeadline,
  formatAutonomousApprovalStatus,
  formatAutonomousExecutionMode,
  formatAutonomousPhase,
} from "@/lib/incident-resolution-copy";
import type {
  AutonomousApprovalStatus,
  AutonomousExecutionMode,
  AutonomousRun,
  AutonomousRunEvent,
  AutonomousRunStatus,
  IncidentAutonomousRunDetail,
  IncidentSandboxRunDetail,
} from "@/lib/types";

type AutonomousRunPanelProps = {
  incidentId: string;
  initialDetail: IncidentAutonomousRunDetail | null;
  initialSandboxDetail?: IncidentSandboxRunDetail | null;
  variant?: "default" | "embedded" | "hub";
};

export function AutonomousRunPanel({
  incidentId,
  initialDetail,
  initialSandboxDetail = null,
  variant = "default",
}: AutonomousRunPanelProps) {
  const router = useRouter();
  const [detail, setDetail] = useState<IncidentAutonomousRunDetail | null>(initialDetail);
  const [stickyEvents, setStickyEvents] = useState<AutonomousRunEvent[]>(
    () => initialDetail?.events ?? [],
  );
  const [runHistory, setRunHistory] = useState<AutonomousRun[]>(() =>
    initialDetail ? [initialDetail.run] : [],
  );
  const [sandboxDetail, setSandboxDetail] = useState<IncidentSandboxRunDetail | null>(initialSandboxDetail);
  const [connectionState, setConnectionState] = useState<"live" | "reconnecting">("live");
  const [sandboxConnectionState, setSandboxConnectionState] = useState<"live" | "reconnecting" | "idle">("idle");
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const embedded = variant === "embedded";
  const hub = variant === "hub";
  const activeRunId = detail?.run.id ?? null;
  const isActiveRun = detail?.run.status === "running" || detail?.run.status === "queued";
  const streamState = !isActiveRun ? "idle" : connectionState;
  const sandboxRunId = detail?.run.sandbox_run_id ?? sandboxDetail?.run.id ?? null;

  const refreshLatestDetail = useCallback(async () => {
    const response = await fetch(`/api/incidents/${incidentId}/autonomous-runs/latest`, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error("Failed to load the latest autonomous run.");
    }
    const latest = (await response.json()) as IncidentAutonomousRunDetail;
    setDetail(latest);
    return latest;
  }, [incidentId]);

  const refreshRunHistory = useCallback(async () => {
    const response = await fetch(`/api/incidents/${incidentId}/autonomous-runs`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return;
    }
    const runs = (await response.json()) as AutonomousRun[];
    setRunHistory(runs);
  }, [incidentId]);

  async function runJsonAction<T>(path: string, options?: RequestInit): Promise<T> {
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
        // Keep the fallback message.
      }
      throw new Error(message);
    }
    return (await response.json()) as T;
  }

  async function startRun(executionMode: AutonomousExecutionMode) {
    setActionError(null);
    setActiveAction(`start:${executionMode}`);
    try {
      await runJsonAction(`/api/incidents/${incidentId}/autonomous-runs`, {
        method: "POST",
        body: JSON.stringify({
          execution_mode: executionMode,
          allow_writeback: executionMode === "repair_and_propose",
        }),
      });
      await refreshLatestDetail();
      await refreshRunHistory();
      router.refresh();
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
      void refreshRunHistory();
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
      void refreshRunHistory();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to promote autonomous run.");
    } finally {
      setActiveAction(null);
    }
  }

  useEffect(() => {
    if (isActiveRun) {
      return;
    }
    const interval = window.setInterval(() => {
      void refreshLatestDetail().catch(() => {
        // Keep the previous snapshot if refresh fails.
      });
    }, 15000);
    return () => window.clearInterval(interval);
  }, [isActiveRun, refreshLatestDetail]);

  useEffect(() => {
    void refreshRunHistory();
  }, [refreshRunHistory]);

  useEffect(() => {
    if (!activeRunId || !isActiveRun) {
      return;
    }
    const source = new EventSource(
      `/api/incidents/${incidentId}/autonomous-runs/${activeRunId}/events`,
    );
    source.onopen = () => setConnectionState("live");
    source.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data) as IncidentAutonomousRunDetail;
        setDetail(next);
        setConnectionState("live");
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
    return () => source.close();
  }, [activeRunId, incidentId, isActiveRun]);

  useEffect(() => {
    if (!sandboxRunId) {
      setSandboxConnectionState("idle");
      return;
    }
    const source = new EventSource(
      `/api/incidents/${incidentId}/sandbox-runs/${sandboxRunId}/events`,
    );
    source.onopen = () => setSandboxConnectionState("live");
    source.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data) as IncidentSandboxRunDetail;
        setSandboxDetail(next);
        setSandboxConnectionState(
          next.run.status === "running" || next.run.status === "queued" ? "live" : "idle",
        );
        if (next.run.status === "succeeded" || next.run.status === "failed") {
          source.close();
        }
      } catch {
        setSandboxConnectionState("reconnecting");
      }
    };
    source.onerror = () => {
      setSandboxConnectionState("reconnecting");
      source.close();
    };
    return () => source.close();
  }, [incidentId, sandboxRunId]);

  const stickyIncidentIdRef = useRef(incidentId);
  useEffect(() => {
    if (stickyIncidentIdRef.current === incidentId) {
      return;
    }
    stickyIncidentIdRef.current = incidentId;
    setStickyEvents(initialDetail?.events ?? []);
  }, [incidentId, initialDetail]);

  useEffect(() => {
    const incoming = detail?.events;
    if (!incoming || incoming.length === 0) {
      return;
    }
    setStickyEvents((prev) => mergeRunEventsById(prev, incoming));
  }, [detail?.events]);

  useEffect(() => {
    if (!detail?.run) {
      return;
    }
    setRunHistory((prev) => mergeRunsById(prev, [detail.run]));
  }, [detail?.run]);

  const orderedStickyEvents = useMemo(
    () =>
      [...stickyEvents].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      ),
    [stickyEvents],
  );
  const recentEvents = useMemo(() => orderedStickyEvents.slice(-16).reverse(), [orderedStickyEvents]);
  const orderedRunHistory = useMemo(
    () =>
      [...runHistory].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [runHistory],
  );
  const runHistoryCount = orderedRunHistory.length;
  const latestActionEvent = orderedStickyEvents.at(-1) ?? null;
  const recentSandboxSteps = useMemo(
    () => (sandboxDetail?.steps ?? []).slice(-8).reverse(),
    [sandboxDetail],
  );
  const canRetry =
    detail?.run.status === "failed" ||
    detail?.run.status === "cancelled" ||
    detail?.run.status === "succeeded";

  const runStatus = detail?.run.status;
  const stepIndex = detail?.run.loop_state.step_index ?? 0;
  const maxSteps = detail?.run.loop_state.max_steps ?? 0;
  const attemptCount = detail?.run.loop_state.repair_attempt_count ?? 0;
  const maxAttempts = detail?.run.policy.max_repair_attempts ?? 0;
  const latestReview = detail?.run.latest_review ?? detail?.outcome?.latest_review ?? null;
  const progressPct =
    detail && runStatus
      ? runStatus === "succeeded" || runStatus === "failed" || runStatus === "cancelled"
        ? 100
        : maxSteps > 0
          ? Math.min(100, (stepIndex / maxSteps) * 100)
          : 0
      : 0;
  const progressBarTone =
    runStatus === "failed"
      ? "from-[#f87171] to-[#fb923c]"
      : runStatus === "cancelled"
        ? "from-white/30 to-white/20"
        : "from-[#ff6a3d] to-[#ffb253]";
  const stepCaption =
    detail && maxSteps > 0
      ? runStatus === "succeeded"
        ? `Finished after ${stepIndex} step${stepIndex !== 1 ? "s" : ""} · budget ${maxSteps}`
        : runStatus === "failed" || runStatus === "cancelled"
          ? `Stopped at step ${stepIndex} of ${maxSteps}`
          : `Step ${stepIndex} / ${maxSteps}`
      : detail
        ? `Step index ${stepIndex}${maxSteps > 0 ? ` · budget ${maxSteps}` : ""}`
        : null;
  const failureInsight = useMemo(() => deriveFailureInsight(detail), [detail]);

  const panelRing =
    detail &&
    (detail.run.approval_status === "pending" ||
      detail.run.status === "running" ||
      detail.run.status === "queued")
      ? "border-[rgba(255,106,61,0.45)] shadow-[0_0_48px_-16px_rgba(255,106,61,0.35)]"
      : "border-white/[0.08]";

  const approvalBanner =
    detail?.run.approval_status === "pending" ? (
      <Banner tone="warning" compact={hub}>
        <div>
          <p className="text-sm font-semibold text-[#fde68a]">Approval required</p>
          <p className="mt-0.5 text-sm text-white/70">
            The agent paused for manual review. Approve or reject to continue the run.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
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
            variant="danger"
            onClick={() => setApprovalStatus("rejected")}
          />
        </div>
      </Banner>
    ) : null;

  const policyBanner =
    detail?.run.policy_block_reason ? (
      <Banner tone="warning" compact={hub}>
        <div>
          <p className="text-sm font-semibold text-[#fde68a]">Auto-repair blocked</p>
          <p className="mt-0.5 text-sm text-white/70">{detail.run.policy_block_reason}</p>
        </div>
        <span className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-white/70">
          Connect a repo profile or adjust project policy
        </span>
      </Banner>
    ) : null;

  const currentActionBanner =
    detail && latestActionEvent ? (
      <div className="mt-4 rounded-xl border border-[rgba(45,127,249,0.28)] bg-[rgba(45,127,249,0.08)] px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-[#93c5fd]">
          What the agent is doing now
        </p>
        <p className="mt-1 text-sm font-medium text-white/90">
          {latestActionEvent.summary}
        </p>
        <p className="mt-1 text-xs text-white/55">
          {formatAutonomousPhase(latestActionEvent.phase)}
          {latestActionEvent.decision?.selected_tool
            ? ` · ${latestActionEvent.decision.selected_tool}`
            : ""}
        </p>
      </div>
    ) : null;

  if (hub) {
    return (
      <section className="relative overflow-hidden">
        {approvalBanner}
        {policyBanner}
        {currentActionBanner}
        {runHistoryCount > 1 ? (
          <RunHistoryCard runs={orderedRunHistory} compact />
        ) : null}
        {detail ? (
          <>
            <details className="mt-3 rounded-lg border border-white/[0.08] bg-black/20 open:border-white/[0.12]">
              <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-medium text-white/75 transition hover:bg-white/[0.04] [&::-webkit-details-marker]:hidden">
                <span className="flex items-center justify-between gap-2">
                  Run actions
                  <span className="text-white/35 transition group-open:rotate-180">▼</span>
                </span>
              </summary>
              <div className="border-t border-white/[0.06] px-3 py-3">
                <div className="flex flex-wrap gap-2">
                  <ActionButton label="Investigate only" disabled={activeAction !== null} active={activeAction === "start:investigate_only"} onClick={() => startRun("investigate_only")} />
                  <ActionButton label="Repair only" disabled={activeAction !== null} active={activeAction === "start:repair_only"} onClick={() => startRun("repair_only")} />
                  <ActionButton label="Repair + PR/MR" disabled={activeAction !== null} active={activeAction === "start:repair_and_propose"} onClick={() => startRun("repair_and_propose")} />
                  {detail.run.promotion_status === "ready" ? (
                    <ActionButton label="Promote" disabled={activeAction !== null} active={activeAction === "promote"} onClick={promoteRun} />
                  ) : null}
                  {canRetry ? (
                    <ActionButton label="Retry" disabled={activeAction !== null} active={false} onClick={() => startRun(detail.run.execution_mode)} />
                  ) : null}
                </div>
                {detail.run.promotion_url ? (
                  <a
                    href={detail.run.promotion_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 inline-flex text-xs font-medium text-[#86efac] hover:text-[#bbf7d0]"
                  >
                    View created PR →
                  </a>
                ) : null}
                {actionError ? <p className="mt-2 text-sm text-[#fca5a5]">{actionError}</p> : null}
              </div>
            </details>
            {failureInsight ? (
              <FailureInsightCard insight={failureInsight} compact />
            ) : null}
            {detail.run.last_error ? (
              <div className="mt-3 rounded-lg border border-[rgba(248,113,113,0.35)] bg-[rgba(248,113,113,0.08)] px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[#fca5a5]">Last error</p>
                <p className="mt-1 text-sm leading-relaxed text-[#fecaca]">{detail.run.last_error}</p>
              </div>
            ) : null}
          </>
        ) : (
          <div className="flex flex-wrap gap-2">
            <ActionButton label="Investigate only" disabled={activeAction !== null} active={activeAction === "start:investigate_only"} onClick={() => startRun("investigate_only")} />
            <ActionButton label="Repair only" disabled={activeAction !== null} active={activeAction === "start:repair_only"} onClick={() => startRun("repair_only")} />
            <ActionButton label="Repair + PR/MR" disabled={activeAction !== null} active={activeAction === "start:repair_and_propose"} onClick={() => startRun("repair_and_propose")} />
            {actionError ? <p className="w-full text-sm text-[#fca5a5]">{actionError}</p> : null}
          </div>
        )}
      </section>
    );
  }

  return (
    <section
      className={
        embedded
          ? "relative overflow-hidden"
          : `relative overflow-hidden rounded-2xl border bg-[rgba(14,18,28,0.92)] p-5 sm:p-6 ${panelRing}`
      }
    >
      {approvalBanner}
      {policyBanner}

      {embedded ? null : (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                Autonomous resolution
              </p>
              {detail && isActiveRun ? (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[rgba(255,106,61,0.35)] bg-[rgba(255,106,61,0.1)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#ffb99a]">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#ff6a3d] opacity-60" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#ff6a3d]" />
                  </span>
                  Live
                </span>
              ) : null}
              {detail && streamState === "reconnecting" ? (
                <span className="text-[10px] font-medium uppercase tracking-wide text-amber-200/80">
                  Reconnecting…
                </span>
              ) : null}
              {sandboxRunId && sandboxConnectionState !== "idle" ? (
                <span className="text-[10px] font-medium uppercase tracking-wide text-[#93c5fd]">
                  Sandbox {sandboxConnectionState === "live" ? "live" : "reconnecting"}
                </span>
              ) : null}
            </div>
            <h3 className="mt-2 text-lg font-semibold leading-snug text-white">
              {detail ? detail.run.objective : "No autonomous run yet"}
            </h3>
            {detail ? (
              <p className="mt-2 text-sm text-white/55">
                {autonomousResolutionHeadline({
                  status: detail.run.status,
                  phase: detail.run.phase,
                  approval_status: detail.run.approval_status,
                  execution_mode: detail.run.execution_mode,
                })}
              </p>
            ) : null}
          </div>

          {detail ? (
            <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
              <StatusPill status={detail.run.status} />
              <span className="text-[10px] font-medium uppercase tracking-wider text-white/35">
                {streamState === "live" && isActiveRun
                  ? "Streaming updates"
                  : streamState === "reconnecting"
                    ? "Reconnecting"
                    : "Snapshot"}
              </span>
            </div>
          ) : null}
        </div>
      )}

      {detail ? (
        <>
          <div className="mt-5 rounded-xl border border-white/[0.06] bg-black/20 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <div className="space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-white/35">
                  Run phase
                </p>
                <p className="font-medium text-white">{formatAutonomousPhase(detail.run.phase)}</p>
              </div>
              <div className="text-right text-sm text-white/60">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-white/35">
                  Mode
                </p>
                <p className="font-medium text-white/85">
                  {formatAutonomousExecutionMode(detail.run.execution_mode)}
                </p>
              </div>
            </div>
            <div className="mt-3">
              <div className="mb-1.5 flex items-center justify-between gap-3 text-[11px] text-white/45">
                <span>{stepCaption}</span>
                <span>
                  {detail.run.loop_state.last_tool_name
                    ? `Last tool: ${detail.run.loop_state.last_tool_name}`
                    : "Starting tools…"}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.08]">
                <div
                  className={`h-full rounded-full bg-gradient-to-r transition-[width] duration-500 ease-out ${progressBarTone}`}
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 border-t border-white/[0.06] pt-3 text-[11px] text-white/50">
              <span>Approval: {formatAutonomousApprovalStatus(detail.run.approval_status)}</span>
              <span className="capitalize">Promotion: {detail.run.promotion_status.replace(/_/g, " ")}</span>
              {maxAttempts > 0 ? (
                <span>
                  Attempt: {Math.max(attemptCount, 1)} / {maxAttempts}
                </span>
              ) : null}
              {detail.run.loop_state.recovery_attempts > 0 ? (
                <span>Recovery attempts: {detail.run.loop_state.recovery_attempts}</span>
              ) : null}
              {detail.run.loop_state.stagnation_count > 0 ? (
                <span>Stagnation count: {detail.run.loop_state.stagnation_count}</span>
              ) : null}
            </div>
            {detail.run.loop_state.last_retry_context &&
            Object.keys(detail.run.loop_state.last_retry_context).length > 0 ? (
              <div className="mt-3 rounded-lg border border-[rgba(45,127,249,0.24)] bg-[rgba(45,127,249,0.08)] px-3 py-2.5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[#93c5fd]">
                  Retry memory
                </p>
                <p className="mt-1 text-sm text-white/80">
                  {formatRetryDriver(
                    String(detail.run.loop_state.last_retry_context.retry_driver ?? "unknown"),
                  )}
                </p>
                {typeof detail.run.loop_state.last_retry_context.previous_review_summary === "string" ? (
                  <p className="mt-1 text-sm text-white/60">
                    {detail.run.loop_state.last_retry_context.previous_review_summary}
                  </p>
                ) : typeof detail.run.loop_state.last_retry_context.previous_verification_summary ===
                    "string" ? (
                  <p className="mt-1 text-sm text-white/60">
                    {detail.run.loop_state.last_retry_context.previous_verification_summary}
                  </p>
                ) : null}
              </div>
            ) : null}
            {detail.run.loop_state.last_failure ? (
              <div className="mt-3 rounded-lg border border-[rgba(248,113,113,0.25)] bg-[rgba(248,113,113,0.06)] px-3 py-2.5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[#fca5a5]">
                  Last tool failure
                </p>
                <p className="mt-1 text-sm text-white/80">
                  {detail.run.loop_state.last_failure.tool_name} ·{" "}
                  {detail.run.loop_state.last_failure.failure_class.replace(/_/g, " ")}
                </p>
                <p className="mt-1 text-sm text-white/60">
                  {detail.run.loop_state.last_failure.message}
                </p>
                {detail.run.loop_state.last_failure.hint ? (
                  <p className="mt-1 text-xs text-white/45">
                    Hint: {detail.run.loop_state.last_failure.hint}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>

          {currentActionBanner}
          {runHistoryCount > 0 ? (
            <RunHistoryCard runs={orderedRunHistory} />
          ) : null}

          <details className="group mt-4 rounded-xl border border-white/[0.06] bg-black/15">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white/80 transition hover:bg-white/[0.04] [&::-webkit-details-marker]:hidden">
              <span className="flex items-center justify-between gap-2">
                Operator controls
                <span className="text-white/35 transition group-open:rotate-180">▼</span>
              </span>
            </summary>
            <div className="border-t border-white/[0.06] px-4 py-4">
              <div className="flex flex-wrap gap-2">
                <ActionButton label="Investigate only" disabled={activeAction !== null} active={activeAction === "start:investigate_only"} onClick={() => startRun("investigate_only")} />
                <ActionButton label="Repair only" disabled={activeAction !== null} active={activeAction === "start:repair_only"} onClick={() => startRun("repair_only")} />
                <ActionButton label="Repair + PR/MR" disabled={activeAction !== null} active={activeAction === "start:repair_and_propose"} onClick={() => startRun("repair_and_propose")} />
                {detail.run.promotion_status === "ready" ? (
                  <ActionButton label="Promote" disabled={activeAction !== null} active={activeAction === "promote"} onClick={promoteRun} />
                ) : null}
                {canRetry ? (
                  <ActionButton label="Retry" disabled={activeAction !== null} active={false} onClick={() => startRun(detail.run.execution_mode)} />
                ) : null}
              </div>
              {detail.run.promotion_url ? (
                <a
                  href={detail.run.promotion_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-flex text-sm font-medium text-[#86efac] hover:text-[#bbf7d0]"
                >
                  View created PR →
                </a>
              ) : null}
              {actionError ? <p className="mt-3 text-sm text-[#fca5a5]">{actionError}</p> : null}
            </div>
          </details>

          <details className="group mt-3 rounded-xl border border-white/[0.06] bg-black/15">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white/80 transition hover:bg-white/[0.04] [&::-webkit-details-marker]:hidden">
              <span className="flex items-center justify-between gap-2">
                Policy & readiness
                <span className="text-white/35 transition group-open:rotate-180">▼</span>
              </span>
            </summary>
            <div className="border-t border-white/[0.06] px-4 py-4">
              <div className="grid gap-2 text-sm text-white/60">
                <AutonomousMetaRow label="Auto-run allowed" value={detail.run.policy.auto_run_allowed ? "Yes" : "No"} />
                <AutonomousMetaRow label="Write-back allowed" value={detail.run.policy.allow_writeback ? "Yes" : "No"} />
                <AutonomousMetaRow
                  label="Repairability"
                  value={
                    detail.run.policy.repairability_score === null
                      ? "Not assessed"
                      : `${Math.round(detail.run.policy.repairability_score * 100)}% confidence`
                  }
                />
                <AutonomousMetaRow label="Browser verification required" value={detail.run.policy.require_browser_verification ? "Yes" : "No"} />
                <AutonomousMetaRow label="Allowed backends" value={detail.run.policy.allowed_execution_backends.join(", ") || "None"} />
                <AutonomousMetaRow label="Allowed tools" value={detail.run.policy.allowed_tool_categories.join(", ") || "None"} />
                <AutonomousMetaRow label="Repo profile" value={detail.run.repo_profile_id ?? "Not resolved"} />
                <AutonomousMetaRow label="Contract base" value={detail.run.run_contract?.base_commit_sha ?? "Default branch"} />
                <AutonomousMetaRow label="Contract verify" value={detail.run.run_contract?.verify_command ?? "Not configured"} />
                <AutonomousMetaRow label="Patch run" value={detail.run.patch_run_id ?? "Pending"} />
                <AutonomousMetaRow label="Sandbox run" value={detail.run.sandbox_run_id ?? "Pending"} />
              </div>
              {detail.run.run_contract?.trust_notes.length ? (
                <div className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.03] p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                    Run contract
                  </p>
                  <div className="mt-2 space-y-2 text-sm text-white/65">
                    {detail.run.run_contract.trust_notes.map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                  </div>
                </div>
              ) : null}
              {detail.run.policy.reasons.length > 0 ? (
                <div className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.03] p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                    Policy reasons
                  </p>
                  <div className="mt-2 space-y-2 text-sm text-white/65">
                    {detail.run.policy.reasons.map((reason) => (
                      <p key={reason}>{reason}</p>
                    ))}
                  </div>
                </div>
              ) : null}
              {detail.run.policy.repairability_reasons.length > 0 ? (
                <div className="mt-4 rounded-lg border border-[rgba(45,127,249,0.18)] bg-[rgba(45,127,249,0.06)] p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#93c5fd]">
                    Repairability assessment
                  </p>
                  <div className="mt-2 space-y-2 text-sm text-white/65">
                    {detail.run.policy.repairability_reasons.map((reason) => (
                      <p key={reason}>{reason}</p>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </details>

          {detail.outcome ? (
            <details className="group mt-3 rounded-xl border border-white/[0.06] bg-black/15">
              <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white/80 transition hover:bg-white/[0.04] [&::-webkit-details-marker]:hidden">
                <span className="flex items-center justify-between gap-2">
                  Outcome record
                  <span className="text-white/35 transition group-open:rotate-180">▼</span>
                </span>
              </summary>
              <div className="border-t border-white/[0.06] px-4 py-4">
                <div className="grid gap-2 text-sm text-white/65">
                  <AutonomousMetaRow label="Decisions" value={String(detail.outcome.total_decisions)} />
                  <AutonomousMetaRow label="Tool calls" value={String(detail.outcome.total_tool_calls)} />
                  <AutonomousMetaRow label="Completed" value={formatTimestamp(detail.outcome.completed_at)} />
                  <AutonomousMetaRow label="Final success" value={detail.outcome.final_success ? "Yes" : "No"} />
                  <AutonomousMetaRow label="Fresh verification" value={detail.outcome.fresh_verification_satisfied ? "Satisfied" : "Pending"} />
                  <AutonomousMetaRow label="Promotion" value={detail.outcome.promotion_status} />
                </div>
                {detail.outcome.latest_verification ? (
                  <div className="mt-4 rounded-lg border border-[rgba(32,201,51,0.2)] bg-[rgba(32,201,51,0.06)] p-3">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-[#86efac]">
                      Verification summary
                    </p>
                    <p className="mt-1 text-sm text-white/80">
                      {detail.outcome.latest_verification.summary}
                    </p>
                    {detail.outcome.latest_verification.command ? (
                      <p className="mt-1 break-all text-xs text-white/45">
                        {detail.outcome.latest_verification.command}
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </details>
          ) : null}

          {latestReview ? (
            <div className="mt-4 rounded-xl border border-[rgba(45,127,249,0.22)] bg-[rgba(45,127,249,0.08)] px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#93c5fd]">
                    Solution review
                  </p>
                  <p className="mt-1 text-sm font-medium text-white/90">
                    {formatReviewVerdict(latestReview.verdict)}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-white/65">
                    {latestReview.summary}
                  </p>
                </div>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white/60">
                  {latestReview.model_name}
                </span>
              </div>
              {latestReview.risks.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {latestReview.risks.map((risk, index) => (
                    <div
                      key={`${risk.area}-${index}`}
                      className="rounded-lg border border-white/[0.06] bg-black/20 px-3 py-2.5"
                    >
                      <p className="text-sm font-medium text-white/85">
                        {risk.area} · {risk.severity}
                      </p>
                      <p className="mt-1 text-sm text-white/60">{risk.reasoning}</p>
                    </div>
                  ))}
                </div>
              ) : null}
              {latestReview.feedback_for_repair.length > 0 ? (
                <div className="mt-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                    Feedback for next attempt
                  </p>
                  <div className="mt-2 space-y-1.5 text-sm text-white/60">
                    {latestReview.feedback_for_repair.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="mt-4">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
              Live activity
            </p>
            <div className="mt-2 max-h-[32rem] space-y-2 overflow-auto pr-1">
              {recentEvents.length === 0 ? (
                <p className="rounded-lg border border-dashed border-white/[0.08] px-3 py-6 text-center text-sm text-white/40">
                  Events will appear here as the agent runs.
                </p>
              ) : (
                recentEvents.map((event) => <EventCard key={event.id} event={event} />)
              )}
            </div>
          </div>

          {sandboxDetail ? (
            <div className="mt-4 rounded-xl border border-white/[0.06] bg-black/15 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                    Sandbox activity
                  </p>
                  <p className="mt-1 text-sm font-medium text-white/90">
                    {sandboxDetail.run.summary}
                  </p>
                </div>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white/65">
                  {sandboxDetail.run.status}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-3 text-xs text-white/50">
                <span>Patch applied: {sandboxDetail.run.patch_applied ? "Yes" : "No"}</span>
                <span>Reproduced: {sandboxDetail.run.reproduction_succeeded ? "Yes" : "No"}</span>
                <span>Verified: {sandboxDetail.run.verification_succeeded ? "Yes" : "No"}</span>
              </div>
              <div className="mt-3 space-y-2">
                {recentSandboxSteps.length === 0 ? (
                  <p className="text-sm text-white/40">
                    Waiting for sandbox steps…
                  </p>
                ) : (
                  recentSandboxSteps.map((step) => (
                    <div
                      key={step.id}
                      className="rounded-lg border border-white/[0.06] bg-black/25 px-3 py-2.5"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-white/90">{step.step_name}</p>
                          <p className="mt-1 text-sm text-white/55">{step.summary}</p>
                        </div>
                        <span className="text-[10px] uppercase tracking-wide text-white/40">
                          {step.status}
                        </span>
                      </div>
                      {step.command ? (
                        <p className="mt-2 break-all font-mono text-[11px] text-[#a5d4ff]">
                          {step.command}
                        </p>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
              <details className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.03]">
                <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-white/70 [&::-webkit-details-marker]:hidden">
                  Execution log
                </summary>
                <pre className="max-h-64 overflow-auto border-t border-white/[0.06] px-3 py-3 whitespace-pre-wrap font-mono text-xs leading-relaxed text-white/65">
                  {sandboxDetail.run.execution_log || "Execution log pending."}
                </pre>
              </details>
            </div>
          ) : null}

          <details className="group mt-3 rounded-xl border border-white/[0.06] bg-black/15">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white/80 transition hover:bg-white/[0.04] [&::-webkit-details-marker]:hidden">
              <span className="flex items-center justify-between gap-2">
                Artifacts & links
                <span className="text-white/35 transition group-open:rotate-180">▼</span>
              </span>
            </summary>
            <div className="border-t border-white/[0.06] px-4 py-4">
              <div className="grid gap-2 text-sm text-white/65">
                <AutonomousMetaRow label="Snapshot" value={detail.artifact_paths.snapshot_path} />
                <AutonomousMetaRow label="Transcript" value={detail.artifact_paths.events_path} />
                <AutonomousMetaRow label="Outcome" value={detail.artifact_paths.outcome_path ?? "Pending"} />
                <AutonomousMetaRow label="Promotion branch" value={detail.run.promotion_branch_name ?? "Pending"} />
                <AutonomousMetaRow label="Promotion URL" value={detail.run.promotion_url ?? "Pending"} />
              </div>
            </div>
          </details>

          {failureInsight ? <FailureInsightCard insight={failureInsight} /> : null}

          {detail.run.last_error ? (
            <div className="mt-4 rounded-xl border border-[rgba(248,113,113,0.35)] bg-[rgba(248,113,113,0.08)] px-4 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[#fca5a5]">
                Last error
              </p>
              <p className="mt-2 text-sm leading-relaxed text-[#fecaca]">{detail.run.last_error}</p>
            </div>
          ) : null}
        </>
      ) : (
        <div className="mt-5 space-y-4">
          <p className="text-sm leading-relaxed text-white/55">
            Start a regulated autonomous run to investigate or repair this incident. Progress streams here in real time.
          </p>
          <div className="flex flex-wrap gap-2">
            <ActionButton label="Investigate only" disabled={activeAction !== null} active={activeAction === "start:investigate_only"} onClick={() => startRun("investigate_only")} />
            <ActionButton label="Repair only" disabled={activeAction !== null} active={activeAction === "start:repair_only"} onClick={() => startRun("repair_only")} />
            <ActionButton label="Repair + PR/MR" disabled={activeAction !== null} active={activeAction === "start:repair_and_propose"} onClick={() => startRun("repair_and_propose")} />
          </div>
          {actionError ? <p className="text-sm text-[#fca5a5]">{actionError}</p> : null}
        </div>
      )}
    </section>
  );
}

function mergeRunEventsById(
  prev: AutonomousRunEvent[],
  incoming: AutonomousRunEvent[],
): AutonomousRunEvent[] {
  if (prev.length === 0) {
    return [...incoming];
  }
  const byId = new Map<string, AutonomousRunEvent>();
  for (const event of prev) {
    byId.set(event.id, event);
  }
  let changed = false;
  for (const event of incoming) {
    const existing = byId.get(event.id);
    if (!existing) {
      byId.set(event.id, event);
      changed = true;
      continue;
    }
    if (existing !== event) {
      byId.set(event.id, event);
      changed = true;
    }
  }
  if (!changed) {
    return prev;
  }
  return Array.from(byId.values());
}

function mergeRunsById(prev: AutonomousRun[], incoming: AutonomousRun[]): AutonomousRun[] {
  const byId = new Map<string, AutonomousRun>();
  for (const run of prev) {
    byId.set(run.id, run);
  }
  for (const run of incoming) {
    byId.set(run.id, run);
  }
  return Array.from(byId.values());
}

function RunHistoryCard({ runs, compact = false }: { runs: AutonomousRun[]; compact?: boolean }) {
  const visibleRuns = compact ? runs.slice(0, 3) : runs.slice(0, 6);
  const latestRunId = runs[0]?.id;

  return (
    <details className="group mt-3 rounded-xl border border-white/[0.06] bg-black/15">
      <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white/80 transition hover:bg-white/[0.04] [&::-webkit-details-marker]:hidden">
        <span className="flex items-center justify-between gap-2">
          Run history
          <span className="text-xs text-white/40">
            {runs.length} attempt{runs.length === 1 ? "" : "s"}
          </span>
        </span>
      </summary>
      <div className="space-y-2 border-t border-white/[0.06] px-4 py-4">
        {visibleRuns.map((run) => (
          <div
            key={run.id}
            className="rounded-lg border border-white/[0.06] bg-black/25 px-3 py-2.5"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-white/90">
                  {run.id === latestRunId ? "Latest run" : `Run ${run.id.slice(0, 8)}`}
                </p>
                <p className="mt-1 text-xs text-white/45">
                  {formatAutonomousExecutionMode(run.execution_mode)} · {formatTimestamp(run.created_at)}
                </p>
              </div>
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white/60">
                {run.status}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-white/45">
              <span>{formatAutonomousPhase(run.phase)}</span>
              <span>Approval: {formatAutonomousApprovalStatus(run.approval_status)}</span>
              <span className="capitalize">Promotion: {run.promotion_status.replace(/_/g, " ")}</span>
              {run.sandbox_run_id ? <span>Sandbox: {run.sandbox_run_id.slice(0, 8)}</span> : null}
              {run.promotion_url ? (
                <a
                  href={run.promotion_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-[#86efac] hover:text-[#bbf7d0]"
                >
                  PR/MR
                </a>
              ) : null}
            </div>
            {run.last_error ? (
              <p className="mt-2 line-clamp-2 text-xs text-[#fca5a5]">{run.last_error}</p>
            ) : null}
          </div>
        ))}
      </div>
    </details>
  );
}

function EventCard({ event }: { event: AutonomousRunEvent }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-black/25 px-3 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-white/90">{event.summary}</p>
          <p className="mt-1 text-[11px] text-white/45">
            {event.event_type} · {formatAutonomousPhase(event.phase)}
          </p>
        </div>
        <span className="shrink-0 text-[10px] text-white/35">
          {formatTimestamp(event.created_at)}
        </span>
      </div>
      {event.decision ? (
        <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.03] p-3">
          <p className="text-xs font-medium text-white/85">
            {event.decision.action.replace(/_/g, " ")}
            {event.decision.selected_tool ? ` · ${event.decision.selected_tool}` : ""}
          </p>
          {event.decision.rationale ? (
            <p className="mt-1 text-sm text-white/65">{event.decision.rationale}</p>
          ) : null}
          {Object.keys(event.decision.arguments).length > 0 ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-[11px] font-medium text-[#a5d4ff]">
                Tool arguments
              </summary>
              <pre className="mt-2 whitespace-pre-wrap break-all rounded bg-black/25 p-2 font-mono text-[11px] text-[#a5d4ff]">
                {JSON.stringify(event.decision.arguments, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      ) : null}
      {Object.keys(event.payload).length > 0 ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] font-medium text-white/50">
            Event payload
          </summary>
          <pre className="mt-2 whitespace-pre-wrap break-all rounded bg-black/25 p-2 font-mono text-[11px] text-white/60">
            {JSON.stringify(event.payload, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

type FailureInsight = {
  label: string;
  summary: string;
  retryNote: string;
};

function FailureInsightCard({
  insight,
  compact = false,
}: {
  insight: FailureInsight;
  compact?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border border-[rgba(248,113,113,0.28)] bg-[rgba(248,113,113,0.08)] ${
        compact ? "mt-3 px-3 py-2.5" : "mt-4 px-4 py-3"
      }`}
    >
      <p className="text-[10px] font-semibold uppercase tracking-wider text-[#fca5a5]">
        Failure analysis
      </p>
      <p className="mt-1 text-sm font-medium text-[#fee2e2]">{insight.label}</p>
      <p className="mt-1 text-sm leading-relaxed text-white/70">{insight.summary}</p>
      <p className="mt-2 text-xs leading-relaxed text-white/50">{insight.retryNote}</p>
    </div>
  );
}

function deriveFailureInsight(detail: IncidentAutonomousRunDetail | null): FailureInsight | null {
  if (!detail) {
    return null;
  }

  const run = detail.run;
  const lastFailure = run.loop_state.last_failure;
  const derivedFailureClass = detail.outcome?.failure_class ?? lastFailure?.failure_class ?? null;
  const latestVerification = run.latest_verification;
  const latestReview = run.latest_review ?? detail.outcome?.latest_review ?? null;
  const verificationSummary = latestVerification?.summary ?? "";
  const verificationSummaryLower = verificationSummary.toLowerCase();
  const lastError = run.last_error ?? "";
  const lastErrorLower = lastError.toLowerCase();
  const patchApplied = latestVerification?.metadata?.patch_applied;
  const reproductionSucceeded = latestVerification?.metadata?.reproduction_succeeded;
  const isRetryable =
    derivedFailureClass === "validation" ||
    derivedFailureClass === "tool_error" ||
    derivedFailureClass === "exception" ||
    derivedFailureClass === "stagnation" ||
    (patchApplied === false && reproductionSucceeded === true) ||
    verificationSummaryLower.includes("sandbox install step failed before reproduction") ||
    verificationSummaryLower.includes("sandbox failed to restore the requested baseline before verification");

  if (patchApplied === false && reproductionSucceeded === true) {
    return {
      label: "Patch apply failed",
      summary:
        "The sandbox reproduced the bug, but the generated patch could not be applied cleanly against the verification workspace.",
      retryNote:
        "Automatic retry budget is exhausted for this run. Use Retry after reviewing the patch target or repository baseline.",
    };
  }

  if (lastErrorLower.includes("repository root does not exist")) {
    return {
      label: "Repository setup unavailable",
      summary:
        "The sandbox could not locate a valid repository root for this service, so verification could not start.",
      retryNote:
        "Automatic retry is blocked until the repo connection or repository-root configuration is fixed.",
    };
  }

  if (run.policy_block_reason) {
    return {
      label: "Policy blocked autonomous repair",
      summary: run.policy_block_reason,
      retryNote:
        "Automatic retry is blocked by project policy. Adjust the policy or repo linkage before trying again.",
    };
  }

  if (
    latestReview?.verdict === "needs_changes" &&
    (run.status === "failed" || run.status === "cancelled")
  ) {
    return {
      label: "Reviewer requested changes",
      summary: latestReview.summary,
      retryNote:
        "The patch looked promising, but the reviewer flagged risk or missing confidence. The next retry should address the review feedback before promotion.",
    };
  }

  if (
    verificationSummaryLower.includes("sandbox install step failed before reproduction") ||
    verificationSummaryLower.includes("sandbox failed to restore the requested baseline before verification")
  ) {
    return {
      label: "Sandbox setup failed",
      summary:
        verificationSummary ||
        lastError ||
        "The sandbox could not complete setup before verification began.",
      retryNote:
        "Automatic retry budget is exhausted for this run. Retry may succeed if the sandbox environment was transiently unstable.",
    };
  }

  if (derivedFailureClass != null) {
    return {
      label: formatFailureClassLabel(derivedFailureClass),
      summary:
        lastFailure?.message ||
        verificationSummary ||
        lastError ||
        "The autonomous run stopped after a classified tool or verification failure.",
      retryNote: isRetryable
        ? "Automatic retry budget is exhausted for this run. You can try again from the latest incident state."
        : "Automatic retry is blocked for this failure type. Review the failure details before trying again.",
    };
  }

  if (run.status === "failed" && (verificationSummary || lastError)) {
    return {
      label: "Run failed",
      summary: verificationSummary || lastError,
      retryNote:
        "Automatic retry was not attempted because the failure did not match a retryable class. Use Retry after reviewing the failure details.",
    };
  }

  return null;
}

function formatFailureClassLabel(failureClass: string): string {
  return failureClass
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function formatRetryDriver(driver: string): string {
  return driver
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function formatReviewVerdict(verdict: string): string {
  return verdict
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function Banner({
  children,
  tone,
  compact,
}: {
  children: React.ReactNode;
  tone: "warning" | "danger";
  compact?: boolean;
}) {
  const toneClass =
    tone === "danger"
      ? "border-[rgba(248,113,113,0.35)] bg-[rgba(248,113,113,0.08)]"
      : "border-[rgba(255,178,83,0.35)] bg-[rgba(255,178,83,0.08)]";
  return (
    <div
      className={`${compact ? "mb-3 rounded-lg px-3 py-2.5" : "mb-5 rounded-xl px-4 py-3"} flex flex-col gap-3 border sm:flex-row sm:items-center sm:justify-between ${toneClass}`}
    >
      {children}
    </div>
  );
}

function StatusPill({ status }: { status: AutonomousRunStatus }) {
  const styles: Record<AutonomousRunStatus, string> = {
    queued: "border-white/15 bg-white/[0.08] text-white/70",
    running: "border-[rgba(59,130,246,0.4)] bg-[rgba(59,130,246,0.12)] text-[#93c5fd]",
    succeeded: "border-[rgba(34,197,94,0.4)] bg-[rgba(34,197,94,0.1)] text-[#86efac]",
    failed: "border-[rgba(248,113,113,0.4)] bg-[rgba(248,113,113,0.1)] text-[#fecaca]",
    cancelled: "border-white/15 bg-white/[0.06] text-white/50",
  };
  return (
    <span
      className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-wider ${styles[status]}`}
    >
      {status}
    </span>
  );
}

function AutonomousMetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/[0.06] py-2 last:border-b-0">
      <span className="text-white/45">{label}</span>
      <span className="max-w-[65%] break-all text-right font-medium text-white/85">{value}</span>
    </div>
  );
}

function ActionButton({
  label,
  disabled,
  active,
  onClick,
  variant = "default",
}: {
  label: string;
  disabled: boolean;
  active: boolean;
  onClick: () => void;
  variant?: "default" | "danger";
}) {
  const isDanger = variant === "danger";
  let cls =
    "rounded-lg border px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ";
  if (active) {
    cls += isDanger
      ? "border-red-400/50 bg-red-500/25 text-white"
      : "border-[rgba(255,106,61,0.45)] bg-[rgba(255,106,61,0.2)] text-white";
  } else if (isDanger) {
    cls +=
      "border-[rgba(248,113,113,0.35)] bg-[rgba(248,113,113,0.12)] text-[#fecaca] hover:bg-[rgba(248,113,113,0.18)]";
  } else {
    cls += "border-white/[0.12] bg-white/[0.06] text-white/90 hover:bg-white/[0.1]";
  }

  return (
    <button type="button" disabled={disabled} onClick={onClick} className={cls}>
      {active ? "Working…" : label}
    </button>
  );
}
