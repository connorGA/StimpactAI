import { notFound } from "next/navigation";

import { AutonomousRunPanel } from "@/components/autonomous-run-panel";
import { ChatPanel } from "@/components/chat-panel";
import { IncidentCauseNarrative } from "@/components/incident-cause-narrative";
import { IncidentDetailTechnicalDetails } from "@/components/incident-detail-technical-details";
import { UnifiedDiffView } from "@/components/unified-diff-view";
import {
  AgentPlatformError,
  getIncident,
  getLatestIncidentAutonomousRunDetail,
  getIncidentClassification,
  getIncidentPatch,
  getIncidentRootCause,
  getIncidentSandboxRunDetail,
  listIncidentSandboxRuns,
} from "@/lib/agent-platform";
import type {
  IncidentAutonomousRunDetail,
} from "@/lib/types";
import { DashboardMetricCard } from "@/components/dashboard-metric-cards";

export const dynamic = "force-dynamic";

type IncidentDetailPageProps = {
  params: Promise<{
    incidentId: string;
  }>;
};

export default async function IncidentDetailPage({ params }: IncidentDetailPageProps) {
  const { incidentId } = await params;
  let detail;
  let classification;
  let rootCause: Awaited<ReturnType<typeof getIncidentRootCause>>;
  let patch: Awaited<ReturnType<typeof getIncidentPatch>>;
  let sandboxRuns: Awaited<ReturnType<typeof listIncidentSandboxRuns>> = [];
  let latestSandboxDetail: Awaited<ReturnType<typeof getIncidentSandboxRunDetail>> | null = null;
  let latestAutonomousRunDetail: IncidentAutonomousRunDetail | null = null;

  try {
    [detail, classification, rootCause, patch, sandboxRuns] = await Promise.all([
      getIncident(incidentId, { eventLimit: 100 }),
      getIncidentClassification(incidentId, { eventLimit: 50 }),
      getIncidentRootCause(incidentId, { eventLimit: 50 }),
      getIncidentPatch(incidentId, { eventLimit: 50 }),
      listIncidentSandboxRuns(incidentId, { limit: 10 }).catch((caughtError) => {
        if (caughtError instanceof AgentPlatformError && caughtError.status === 404) {
          return [];
        }
        throw caughtError;
      }),
    ]);
  } catch (caughtError) {
    if (caughtError instanceof AgentPlatformError && caughtError.status === 404) {
      notFound();
    }
    throw caughtError;
  }
  const { incident, events } = detail;

  const sandboxDetailPromise =
    sandboxRuns.length > 0
      ? getIncidentSandboxRunDetail(incidentId, sandboxRuns[0].id).catch((caughtError) => {
          if (caughtError instanceof AgentPlatformError && caughtError.status === 404) {
            return null;
          }
          throw caughtError;
        })
      : Promise.resolve(null);

  const autonomousDetailPromise = getLatestIncidentAutonomousRunDetail(incidentId).catch((caughtError) => {
    if (caughtError instanceof AgentPlatformError && caughtError.status === 404) {
      return null;
    }
    throw caughtError;
  });

  const [sandboxResolved, autonomousResolved] = await Promise.all([sandboxDetailPromise, autonomousDetailPromise]);
  latestSandboxDetail = sandboxResolved;
  latestAutonomousRunDetail = autonomousResolved;

  const primarySignal = events[0]?.error_message?.trim() ?? null;
  const run = latestAutonomousRunDetail?.run;
  const outcome = latestAutonomousRunDetail?.outcome;
  const showLiveStrip = Boolean(
    incident.status === "open" &&
      run &&
      (run.status === "running" || run.status === "queued" || run.approval_status === "pending"),
  );
  const showSolvedHero = Boolean(
    run?.status === "succeeded" &&
      outcome?.fresh_verification_satisfied &&
      run?.promotion_url,
  );
  const showFixReadyHero = Boolean(run?.status === "succeeded" && !showSolvedHero);

  const whatWasWrong = [classification.summary.trim(), rootCause.reasoning.root_cause_hypothesis.trim()]
    .filter(Boolean)
    .filter((p, i, arr) => arr.indexOf(p) === i)
    .join("\n\n");

  const rootCauseNarrative =
    (outcome?.root_cause_explanation?.trim() || "") ||
    rootCause.reasoning.reasoning_summary ||
    "Root cause analysis is still running or was not available for this incident.";

  const theFix =
    (outcome?.solution_description?.trim() || "") ||
    patch.rationale ||
    (patch.unified_diff.trim() ? "See the code changes below for the agent’s proposed edits." : "No fix has been generated yet for this incident.");

  return (
    <main className="mx-auto max-w-[1120px] space-y-8 px-2 pb-14 pt-2">
      <IncidentCauseNarrative
        incident={incident}
        primarySignal={primarySignal}
        classification={classification}
        rootCause={rootCause}
        rootCauseNarrative={rootCauseNarrative}
        whatWasWrong={whatWasWrong}
        theFix={theFix}
        latestAutonomousRunDetail={latestAutonomousRunDetail}
        showSolvedStrip={showSolvedHero}
        showFixReadyStrip={showFixReadyHero}
        showLiveStrip={showLiveStrip}
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <DashboardMetricCard label="Status" value={incident.status} />
        <DashboardMetricCard label="Severity" value={incident.severity} />
        <DashboardMetricCard label="Events" value={String(incident.event_count)} />
        <DashboardMetricCard
          label="Latest telemetry"
          value={incident.latest_telemetry_id.length > 12 ? `${incident.latest_telemetry_id.slice(0, 12)}…` : incident.latest_telemetry_id}
        />
      </div>

      <section id="code-changes" className="scroll-mt-24 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-white">Code changes</h2>
            <p className="mt-1 text-sm text-white/50">
              Unified diff for the latest patch. Additions in green, removals in red, context unchanged.
            </p>
          </div>
          {patch.based_on_commit_sha ? (
            <p className="text-[11px] text-white/40">Base: {patch.based_on_commit_sha}</p>
          ) : null}
        </div>
        {patch.target_files.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {patch.target_files.map((f) => (
              <span
                key={f.path}
                className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[11px] text-[#93c5fd]"
              >
                {f.path}
              </span>
            ))}
          </div>
        ) : null}
        {patch.status === "failed" && !patch.unified_diff.trim() ? (
          <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100/90">
            Patch generation did not return a diff. See technical details for logs and model output.
          </div>
        ) : (
          <UnifiedDiffView diff={patch.unified_diff} />
        )}
      </section>

      <AutonomousRunPanel
        incidentId={incident.id}
        initialDetail={latestAutonomousRunDetail}
        initialSandboxDetail={latestSandboxDetail}
        variant="hub"
      />

      <IncidentDetailTechnicalDetails
        events={events}
        classification={classification}
        rootCause={rootCause}
        patch={patch}
        sandboxRuns={sandboxRuns}
        latestSandboxDetail={latestSandboxDetail}
      />

      <ChatPanel
        variant="dark"
        title="Ask about this incident"
        description="Grounded answers from stored events, traces, and analysis for this incident."
        endpoint={`/api/incidents/${incident.id}/chat`}
        extraBody={{
          event_limit: 50,
        }}
        suggestedPrompts={[
          "Summarize the likely root problem in this incident.",
          "What evidence from the recent events is most important?",
          "What debugging steps should an engineer take next for this incident?",
        ]}
        className="min-h-[28rem]"
      />
    </main>
  );
}
