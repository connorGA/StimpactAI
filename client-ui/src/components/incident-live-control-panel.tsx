"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { AutonomousRunPanel } from "@/components/autonomous-run-panel";
import { IncidentStatusActions } from "@/components/incident-status-actions";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { autonomousResolutionHeadline, formatAutonomousPhase } from "@/lib/incident-resolution-copy";
import { formatTimestamp } from "@/lib/dashboard";
import type {
  AutonomousRunEvent,
  IncidentAutonomousRunDetail,
  IncidentSummary,
} from "@/lib/types";

type IncidentLiveControlPanelProps = {
  incident: IncidentSummary;
  initialAutonomousDetail: IncidentAutonomousRunDetail | null;
};

export function IncidentLiveControlPanel({
  incident,
  initialAutonomousDetail,
}: IncidentLiveControlPanelProps) {
  const [detail, setDetail] = useState<IncidentAutonomousRunDetail | null>(initialAutonomousDetail);
  const [stickyEvents, setStickyEvents] = useState<AutonomousRunEvent[]>(
    () => initialAutonomousDetail?.events ?? [],
  );

  const stickyIncidentIdRef = useRef(incident.id);
  useEffect(() => {
    setDetail(initialAutonomousDetail);
    if (stickyIncidentIdRef.current !== incident.id) {
      stickyIncidentIdRef.current = incident.id;
      setStickyEvents(initialAutonomousDetail?.events ?? []);
    }
  }, [initialAutonomousDetail, incident.id]);

  const refreshLatestDetail = useCallback(async () => {
    const response = await fetch(`/api/incidents/${incident.id}/autonomous-runs/latest`, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error("Failed to load the latest autonomous run.");
    }
    const latest = (await response.json()) as IncidentAutonomousRunDetail;
    setDetail(latest);
    return latest;
  }, [incident.id]);

  useEffect(() => {
    void refreshLatestDetail().catch(() => {});
  }, [incident.id, refreshLatestDetail]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refreshLatestDetail().catch(() => {});
    }, 15_000);
    return () => window.clearInterval(interval);
  }, [incident.id, refreshLatestDetail]);

  useEffect(() => {
    if (!detail?.run.id) return;
    const isActiveRun = detail.run.status === "running" || detail.run.status === "queued";
    if (!isActiveRun) return;

    const source = new EventSource(
      `/api/incidents/${incident.id}/autonomous-runs/${detail.run.id}/events`,
    );
    source.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data) as IncidentAutonomousRunDetail;
        setDetail(next);
      } catch {
        // Ignore malformed payloads.
      }
    };
    source.onerror = () => {
      source.close();
    };
    return () => {
      source.close();
    };
  }, [detail?.run.id, detail?.run.status, incident.id]);

  const phaseSteps = useMemo(() => buildPhaseSteps(detail), [detail]);
  const runStatus = detail?.run.status ?? null;
  const isLiveRun = runStatus === "running" || runStatus === "queued";
  const failedStepIndex = phaseSteps.findIndex((step) => step.state === "failed");
  const isResolutionFailed = failedStepIndex >= 0;
  const currentStepIndex = phaseSteps.findIndex((step) => step.state === "current");
  const isResolutionComplete =
    phaseSteps.length > 0 && phaseSteps.every((step) => step.state === "done");
  const activeSegmentIndex =
    isResolutionComplete || isResolutionFailed || currentStepIndex < 0
      ? null
      : Math.max(0, currentStepIndex - 1);

  const headline = detail
    ? autonomousResolutionHeadline({
        status: detail.run.status,
        phase: detail.run.phase,
        approval_status: detail.run.approval_status,
        execution_mode: detail.run.execution_mode,
      })
    : null;

  useEffect(() => {
    const incoming = detail?.events;
    if (!incoming || incoming.length === 0) {
      return;
    }
    setStickyEvents((prev) => mergeRunEventsById(prev, incoming));
  }, [detail?.events]);

  const activityEvents = useMemo(
    () =>
      [...stickyEvents].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      ),
    [stickyEvents],
  );

  const runProgress = useMemo(
    () => runRingProgress(phaseSteps, runStatus, isResolutionComplete),
    [phaseSteps, runStatus, isResolutionComplete],
  );

  const connectorStateAt = (index: number): PhaseConnectorState => {
    if (index === phaseSteps.length - 1) return null;
    if (isResolutionComplete) return "complete";
    if (isResolutionFailed) {
      if (index < failedStepIndex) return "done";
      return "upcoming";
    }
    if (activeSegmentIndex === index) return "current";
    if (index < (activeSegmentIndex ?? -1)) return "done";
    return "upcoming";
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[linear-gradient(180deg,rgba(16,20,30,0.95),rgba(10,14,22,0.98))]">
      <div className="flex flex-col gap-4 px-4 py-4 sm:px-5 sm:py-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">Open incident</p>
            <h2 className="mt-1 line-clamp-2 text-base font-semibold leading-snug text-white sm:text-lg">
              {incident.title}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <SeverityBadge severity={incident.severity} />
              <StatusBadge status={incident.status} />
              {isLiveRun ? (
                <span className="rounded-full border border-[#ff6a3d]/35 bg-[#ff6a3d]/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#ffb99a]">
                  Live
                </span>
              ) : null}
            </div>
            {headline ? (
              <p className="mt-2 line-clamp-2 text-sm text-white/50">{headline}</p>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1.5 sm:pt-0">
            <Link
              href={`/incidents/${incident.id}`}
              className="text-xs font-medium text-[#ff8c5a] transition hover:text-[#ffb99a]"
            >
              Details →
            </Link>
            <IncidentStatusActions incidentId={incident.id} status={incident.status} compact />
            <IncidentResponseTimer
              firstSeenAt={incident.first_seen_at}
              detail={detail}
              runProgress={runProgress}
            />
          </div>
        </div>

        <div className="lg:hidden">
          <div className="space-y-3">
            {phaseSteps.map((step, index) => (
              <PhaseRailStep
                key={step.label}
                step={step}
                index={index}
                isLast={index === phaseSteps.length - 1}
                compact
                connectorState={connectorStateAt(index)}
              />
            ))}
          </div>
        </div>

        <div className="relative hidden lg:block">
          <div className="pointer-events-none absolute left-[10%] right-[10%] top-4 h-px bg-white/[0.08]" />
          <div className="grid grid-cols-4 gap-4">
            {phaseSteps.map((step, index) => (
              <PhaseRailStep
                key={step.label}
                step={step}
                index={index}
                isLast={index === phaseSteps.length - 1}
                compact
                connectorState={connectorStateAt(index)}
              />
            ))}
          </div>
        </div>

        <AgentActivityFeed events={activityEvents} isLive={isLiveRun} />

        <AutonomousRunPanel
          key={incident.id}
          incidentId={incident.id}
          initialDetail={detail}
          variant="hub"
        />
      </div>
    </section>
  );
}

type PhaseStepState = "done" | "current" | "upcoming" | "failed";
type PhaseConnectorState = "done" | "current" | "upcoming" | "complete" | "failed" | null;

const IDLE_HUB_PHASE_STEPS: Array<{
  label: string;
  title: string;
  detail: string;
  state: PhaseStepState;
}> = [
  { label: "Signal", title: "Detected", detail: "", state: "upcoming" },
  { label: "Analyze", title: "Analyze", detail: "", state: "upcoming" },
  { label: "Validate", title: "Sandbox", detail: "", state: "upcoming" },
  { label: "Deliver", title: "Deliver", detail: "", state: "upcoming" },
];

/** Same shell as {@link IncidentLiveControlPanel} when the project has no open incidents. */
export function IncidentHubIdleHero() {
  const gradientId = useId().replace(/:/g, "");
  return (
    <section className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[linear-gradient(180deg,rgba(16,20,30,0.95),rgba(10,14,22,0.98))]">
      <div className="flex flex-col gap-4 px-4 py-4 sm:px-5 sm:py-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">Open incident</p>
            <h2 className="mt-1 text-base font-semibold leading-snug text-white sm:text-lg">No active incidents</h2>
            <p className="mt-2 text-sm text-white/45">
              Nothing is demanding attention right now. The next open incident will appear here with live progress and
              agent activity.
            </p>
            <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-[rgba(32,201,51,0.25)] bg-[rgba(32,201,51,0.08)] px-2.5 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-[#20c933]" />
              <span className="text-[10px] font-semibold uppercase tracking-wide text-[#86efac]">Queue clear</span>
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1.5 sm:pt-0">
            <Link
              href="/incidents"
              className="text-xs font-medium text-[#ff8c5a] transition hover:text-[#ffb99a]"
            >
              Incident history →
            </Link>
            <div className="flex flex-col items-end gap-1.5">
              <div className="relative h-[5.75rem] w-[5.75rem] shrink-0" aria-hidden>
                <svg
                  className="h-full w-full drop-shadow-[0_4px_14px_rgba(0,0,0,0.45)]"
                  viewBox="0 0 100 100"
                >
                  <defs>
                    <linearGradient id={`idle-hub-green-${gradientId}`} x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#22c55e" stopOpacity={0.85} />
                      <stop offset="100%" stopColor="#15803d" stopOpacity={0.95} />
                    </linearGradient>
                  </defs>
                  <g transform={`rotate(-90 ${RING_CX} ${RING_CY})`}>
                    <circle
                      cx={RING_CX}
                      cy={RING_CY}
                      r={RING_RADIUS}
                      fill="none"
                      stroke="rgba(255,255,255,0.07)"
                      strokeWidth={4}
                    />
                    <circle
                      cx={RING_CX}
                      cy={RING_CY}
                      r={RING_RADIUS}
                      fill="none"
                      stroke={`url(#idle-hub-green-${gradientId})`}
                      strokeWidth={4}
                      strokeLinecap="round"
                      style={{ strokeDasharray: RING_CIRC, strokeDashoffset: 0 }}
                    />
                  </g>
                </svg>
                <div
                  className="pointer-events-none absolute inset-[11px] rounded-full border border-white/[0.06] shadow-[inset_0_2px_10px_rgba(0,0,0,0.5)]"
                  style={{
                    background:
                      "repeating-conic-gradient(from 0deg, rgba(255,255,255,0.045) 0deg 4deg, transparent 4deg 8deg), linear-gradient(180deg, rgba(255,255,255,0.05), rgba(0,0,0,0.45))",
                  }}
                />
                <div className="absolute inset-0 flex items-center justify-center px-1.5">
                  <span className="font-mono text-[1.05rem] font-bold leading-none tabular-nums tracking-tight text-white/50">
                    —
                  </span>
                </div>
              </div>
              <p className="max-w-[10rem] text-right text-[10px] font-medium uppercase tracking-wide text-white/40">
                No active signal
              </p>
            </div>
          </div>
        </div>

        <div className="lg:hidden">
          <div className="space-y-3">
            {IDLE_HUB_PHASE_STEPS.map((step, index) => (
              <PhaseRailStep
                key={step.label}
                step={step}
                index={index}
                isLast={index === IDLE_HUB_PHASE_STEPS.length - 1}
                compact
                connectorState={
                  index === IDLE_HUB_PHASE_STEPS.length - 1
                    ? null
                    : "upcoming"
                }
              />
            ))}
          </div>
        </div>

        <div className="relative hidden lg:block">
          <div className="pointer-events-none absolute left-[10%] right-[10%] top-4 h-px bg-white/[0.08]" />
          <div className="grid grid-cols-4 gap-4">
            {IDLE_HUB_PHASE_STEPS.map((step, index) => (
              <PhaseRailStep
                key={step.label}
                step={step}
                index={index}
                isLast={index === IDLE_HUB_PHASE_STEPS.length - 1}
                compact
                connectorState={
                  index === IDLE_HUB_PHASE_STEPS.length - 1 ? null : "upcoming"
                }
              />
            ))}
          </div>
        </div>

        <AgentActivityFeed events={[]} isLive={false} />

        <div className="rounded-lg border border-dashed border-white/[0.1] bg-black/15 px-3 py-4 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-white/35">Run actions</p>
          <p className="mt-1 text-xs text-white/40">
            Autonomous repair controls appear when an open incident is in focus.
          </p>
        </div>
      </div>
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

function runRingProgress(
  phaseSteps: Array<{ state: string }>,
  runStatus: string | null,
  isResolutionComplete: boolean,
): number {
  if (isResolutionComplete || runStatus === "succeeded") {
    return 1;
  }
  if (phaseSteps.length === 0) {
    return 0.06;
  }
  const n = phaseSteps.length;
  const done = phaseSteps.filter((step) => step.state === "done").length;
  const hasCurrent = phaseSteps.some((step) => step.state === "current");
  const hasFailed = phaseSteps.some((step) => step.state === "failed");
  const segment = 1 / n;
  const partial = hasCurrent ? segment * 0.42 : hasFailed ? segment * 0.75 : 0;
  return Math.min(0.96, done * segment + partial);
}

const RING_RADIUS = 40;
const RING_CX = 50;
const RING_CY = 50;
const RING_CIRC = 2 * Math.PI * RING_RADIUS;

function IncidentResponseTimer({
  firstSeenAt,
  detail,
  runProgress,
}: {
  firstSeenAt: string;
  detail: IncidentAutonomousRunDetail | null;
  runProgress: number;
}) {
  const startMs = useMemo(() => new Date(firstSeenAt).getTime(), [firstSeenAt]);
  const endMs = useMemo(() => {
    if (!detail) return null;
    if (detail.run.status === "succeeded") {
      return new Date(detail.outcome?.completed_at ?? detail.run.updated_at).getTime();
    }
    if (detail.run.status === "failed" || detail.run.status === "cancelled") {
      return new Date(detail.run.updated_at).getTime();
    }
    return null;
  }, [detail]);

  const isLive = endMs == null;

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!isLive) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isLive]);

  const elapsedMs = Math.max(0, (endMs ?? now) - startMs);
  const main = formatStopwatchMain(elapsedMs);

  const isComplete = detail?.run.status === "succeeded";
  const progress = isComplete ? 1 : Math.max(0.02, Math.min(1, runProgress));
  const thumbRad = -Math.PI / 2 + 2 * Math.PI * progress;
  const thumbX = RING_CX + RING_RADIUS * Math.cos(thumbRad);
  const thumbY = RING_CY + RING_RADIUS * Math.sin(thumbRad);

  return (
    <div className="flex flex-col items-end gap-1.5">
      <div
        className="relative h-[5.75rem] w-[5.75rem] shrink-0"
        role="timer"
        aria-live="polite"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        aria-label={`Elapsed time ${main}, run progress ${Math.round(progress * 100)} percent`}
      >
        <svg
          className="h-full w-full drop-shadow-[0_4px_14px_rgba(0,0,0,0.45)]"
          viewBox="0 0 100 100"
          aria-hidden
        >
          <defs>
            <linearGradient id="incident-ring-orange" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#ff6a3d" stopOpacity={0.95} />
              <stop offset="55%" stopColor="#ff8c5a" stopOpacity={1} />
              <stop offset="100%" stopColor="#c2410c" stopOpacity={0.85} />
            </linearGradient>
            <linearGradient id="incident-ring-green" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#22c55e" stopOpacity={0.95} />
              <stop offset="100%" stopColor="#15803d" stopOpacity={1} />
            </linearGradient>
          </defs>
          <g transform={`rotate(-90 ${RING_CX} ${RING_CY})`}>
            <circle
              cx={RING_CX}
              cy={RING_CY}
              r={RING_RADIUS}
              fill="none"
              stroke="rgba(255,255,255,0.07)"
              strokeWidth={4}
            />
            {isComplete ? (
              <circle
                cx={RING_CX}
                cy={RING_CY}
                r={RING_RADIUS}
                fill="none"
                stroke="url(#incident-ring-green)"
                strokeWidth={4}
                strokeLinecap="round"
                style={{
                  strokeDasharray: RING_CIRC,
                  strokeDashoffset: 0,
                }}
              />
            ) : (
              <circle
                cx={RING_CX}
                cy={RING_CY}
                r={RING_RADIUS}
                fill="none"
                stroke="url(#incident-ring-orange)"
                strokeWidth={4}
                strokeLinecap="round"
                className="transition-[stroke-dashoffset] duration-500"
                style={{
                  strokeDasharray: RING_CIRC,
                  strokeDashoffset: RING_CIRC * (1 - progress),
                }}
              />
            )}
          </g>
          {!isComplete && progress > 0.02 && progress < 0.999 ? (
            <circle
              cx={thumbX}
              cy={thumbY}
              r={3.25}
              fill="#ff8c5a"
              className="drop-shadow-[0_0_6px_rgba(255,106,61,0.65)]"
            />
          ) : null}
        </svg>
        <div
          className="pointer-events-none absolute inset-[11px] rounded-full border border-white/[0.06] shadow-[inset_0_2px_10px_rgba(0,0,0,0.5)]"
          style={{
            background:
              "repeating-conic-gradient(from 0deg, rgba(255,255,255,0.045) 0deg 4deg, transparent 4deg 8deg), linear-gradient(180deg, rgba(255,255,255,0.05), rgba(0,0,0,0.45))",
          }}
        />
        <div className="absolute inset-0 flex items-center justify-center px-1.5">
          <span className="font-mono text-[1.05rem] font-bold leading-none tabular-nums tracking-tight text-white">
            {main}
          </span>
        </div>
      </div>
      <p className="max-w-[10rem] text-right text-[10px] font-medium uppercase tracking-wide text-white/40">
        Since first signal
      </p>
    </div>
  );
}

function formatStopwatchMain(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const s = totalSec % 60;
  const totalMin = Math.floor(totalSec / 60);
  const m = totalMin % 60;
  const h = Math.floor(totalMin / 60);
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function AgentActivityFeed({ events, isLive }: { events: AutonomousRunEvent[]; isLive: boolean }) {
  const feedRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = feedRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [events]);

  return (
    <div className="overflow-hidden rounded-lg border border-white/[0.08] bg-black/35">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-3 py-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-white/45">Agent activity</p>
        {isLive ? (
          <span className="text-[10px] font-medium text-[#ffb99a]">
            <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[#ff6a3d]" />
            Streaming
          </span>
        ) : (
          <span className="text-[10px] text-white/35">Latest run</span>
        )}
      </div>
      <div ref={feedRef} className="max-h-60 overflow-y-auto px-2 py-2">
        {events.length === 0 ? (
          <p className="rounded-md border border-dashed border-white/[0.08] px-3 py-8 text-center text-xs text-white/40">
            Agent steps will appear here as the run progresses — tools, files, and decisions stream in
            real time.
          </p>
        ) : (
          <ul className="space-y-0 font-mono text-[11px] leading-relaxed">
            {events.map((event, index) => {
              const hint = fileHintFromEvent(event);
              const tool = event.decision?.selected_tool ?? null;
              const meta = [formatAutonomousPhase(event.phase), tool, event.event_type !== "decision" ? event.event_type : null]
                .filter(Boolean)
                .join(" · ");
              const isLatest = index === events.length - 1;
              return (
                <li
                  key={event.id}
                  className={`border-l-2 py-1.5 pl-2.5 pr-1 ${
                    isLatest && isLive ? "border-[#ff6a3d] bg-[#ff6a3d]/[0.06]" : "border-white/[0.08]"
                  }`}
                >
                  <p className="text-white/88">{event.summary}</p>
                  <p className="mt-0.5 text-[10px] text-white/40">
                    {meta}
                    {hint ? <span className="text-[#86efac]/90"> · {hint}</span> : null}
                    <span className="text-white/25"> · {formatTimestamp(event.created_at)}</span>
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function fileHintFromEvent(event: AutonomousRunEvent): string | null {
  const args = event.decision?.arguments;
  if (args && typeof args === "object") {
    for (const key of ["path", "file", "file_path", "target_path", "uri"]) {
      const v = (args as Record<string, unknown>)[key];
      if (typeof v === "string" && v.length > 0) {
        return v.length > 72 ? `${v.slice(0, 69)}…` : v;
      }
    }
  }
  if (event.decision?.arguments_summary) {
    return event.decision.arguments_summary.length > 80
      ? `${event.decision.arguments_summary.slice(0, 77)}…`
      : event.decision.arguments_summary;
  }
  const p = event.payload;
  if (p && typeof p === "object") {
    for (const key of ["path", "file", "file_path"]) {
      const v = (p as Record<string, unknown>)[key];
      if (typeof v === "string" && v.length > 0) {
        return v.length > 72 ? `${v.slice(0, 69)}…` : v;
      }
    }
  }
  return null;
}

function buildPhaseSteps(detail: IncidentAutonomousRunDetail | null): Array<{
  label: string;
  title: string;
  detail: string;
  state: PhaseStepState;
}> {
  const currentPhase = detail?.run.phase ?? "initializer";
  const status = detail?.run.status ?? null;
  const isCompleted = status === "succeeded" || currentPhase === "completed";
  const isFailed = status === "failed" || status === "cancelled";

  const steps = [
    { label: "Signal", title: "Detected", detail: "" },
    { label: "Analyze", title: "Analyze", detail: "" },
    { label: "Validate", title: "Sandbox", detail: "" },
    { label: "Deliver", title: "Deliver", detail: "" },
  ];

  if (isCompleted) {
    return steps.map((step) => ({ ...step, state: "done" as const }));
  }

  const reachedIndex = inferReachedStepIndex(detail, currentPhase);

  if (isFailed) {
    return steps.map((step, index) => ({
      ...step,
      state:
        index < reachedIndex ? "done" : index === reachedIndex ? "failed" : "upcoming",
    }));
  }

  return steps.map((step, index) => ({
    ...step,
    state:
      index < reachedIndex
        ? "done"
        : index === reachedIndex
          ? "current"
          : "upcoming",
  }));
}

function inferReachedStepIndex(
  detail: IncidentAutonomousRunDetail | null,
  currentPhase: string,
): number {
  const phaseToIndex = (phase: string | null | undefined): number | null => {
    if (phase === "completed") return 3;
    if (phase === "verification" || phase === "recovery") return 2;
    if (phase === "initializer" || phase === "coding") return 1;
    return null;
  };

  const fromCurrent = phaseToIndex(currentPhase);
  if (fromCurrent !== null) return fromCurrent;

  const events = detail?.events ?? [];
  for (let i = events.length - 1; i >= 0; i--) {
    const mapped = phaseToIndex(events[i].phase);
    if (mapped !== null) return mapped;
  }

  const error = (detail?.run.last_error ?? "").toLowerCase();
  if (
    error.includes("sandbox") ||
    error.includes("verification") ||
    error.includes("patch") ||
    error.includes("repository")
  ) {
    return 2;
  }

  return 1;
}

function PhaseRailStep({
  step,
  index,
  isLast,
  compact,
  connectorState,
}: {
  step: {
    label: string;
    title: string;
    detail: string;
    state: PhaseStepState;
  };
  index: number;
  isLast: boolean;
  compact?: boolean;
  connectorState: PhaseConnectorState;
}) {
  const nodeContent =
    step.state === "failed" ? (
      <span aria-hidden className="text-sm leading-none">!</span>
    ) : (
      <>{index + 1}</>
    );

  return (
    <div className="relative flex flex-1 flex-col items-start lg:items-center">
      <div className="flex flex-col items-center">
        <span
          className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold ${
            step.state === "failed"
              ? "border-[#ef4444] bg-[#ef4444]/20 text-[#fecaca] shadow-[0_0_0_3px_rgba(239,68,68,0.12)]"
              : step.state === "current"
                ? "border-[#ff6a3d] bg-[#ff6a3d]/18 text-white"
                : step.state === "done"
                  ? "border-[rgba(32,201,51,0.36)] bg-[rgba(32,201,51,0.12)] text-[#86efac]"
                  : "border-white/[0.08] bg-white/[0.03] text-white/45"
          }`}
        >
          {nodeContent}
        </span>
        {!isLast ? (
          <span
            className={`mt-2 h-6 w-px lg:hidden ${
              connectorState === "complete" || connectorState === "done"
                ? "bg-[#20c933]/50"
                : connectorState === "current"
                  ? "bg-[#ff6a3d]/55"
                  : connectorState === "failed"
                    ? "bg-[#ef4444]/55"
                    : "bg-white/[0.08]"
            }`}
          />
        ) : null}
      </div>
      {!isLast ? (
        <div className="pointer-events-none absolute left-[calc(50%+1rem)] right-[-50%] top-[0.875rem] hidden lg:block">
          <div
            className={`relative h-[3px] overflow-hidden rounded-full ${
              connectorState === "complete" || connectorState === "done"
                ? "bg-[#20c933]/28"
                : connectorState === "current"
                  ? "bg-[#ff6a3d]/22"
                  : connectorState === "failed"
                    ? "bg-[#ef4444]/22"
                    : "bg-white/[0.08]"
            }`}
          >
            {connectorState === "complete" || connectorState === "done" ? (
              <div className="h-full w-full rounded-full bg-[#20c933]/55" />
            ) : null}
            {connectorState === "current" || connectorState === "complete" ? (
              <div
                className={`incident-wire-flow pointer-events-none absolute inset-y-0 w-14 rounded-full ${
                  connectorState === "complete"
                    ? "bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(32,201,51,0.95),rgba(255,255,255,0))]"
                    : "bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,106,61,0.95),rgba(255,255,255,0))]"
                }`}
              />
            ) : null}
          </div>
        </div>
      ) : null}
      <div className={`mt-2 min-w-0 ${compact ? "lg:px-1" : "lg:px-2"} lg:text-center`}>
        <p
          className={`text-[9px] font-semibold uppercase tracking-[0.14em] ${
            step.state === "failed" ? "text-[#fca5a5]" : "text-white/35"
          }`}
        >
          {step.state === "failed" ? `${step.label} · Failed` : step.label}
        </p>
        <p
          className={`mt-0.5 text-xs font-medium ${
            step.state === "failed" ? "text-[#fecaca]" : "text-white/85"
          }`}
        >
          {step.title}
        </p>
        {!compact && step.detail ? (
          <p className="mt-1 max-w-[14rem] text-[11px] leading-relaxed text-white/40">{step.detail}</p>
        ) : null}
      </div>
    </div>
  );
}
