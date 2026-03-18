"use client";

import { useEffect, useMemo, useState } from "react";

import type { IncidentAutonomousRunDetail } from "@/lib/types";
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

  const activeRunId = detail?.run.id ?? null;
  const isActiveRun =
    detail?.run.status === "running" || detail?.run.status === "queued";
  const streamState = !isActiveRun ? "idle" : connectionState;

  useEffect(() => {
    let cancelled = false;

    async function refreshLatest() {
      try {
        const response = await fetch(
          `/api/incidents/${incidentId}/autonomous-runs/latest`,
          { cache: "no-store" },
        );
        if (!response.ok) {
          return;
        }
        const latest = (await response.json()) as IncidentAutonomousRunDetail;
        if (!cancelled) {
          setDetail(latest);
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
  }, [incidentId, isActiveRun]);

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
        <p className="mt-4 text-sm leading-6 text-[#746d66]">
          No autonomous repair run has been persisted for this incident yet. Once
          a run starts, this panel will show the current phase, recent tool use,
          live event timeline, and durable transcript artifacts.
        </p>
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
