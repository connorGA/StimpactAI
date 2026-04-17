import Link from "next/link";
import { notFound } from "next/navigation";

import { AutonomousRunPanel } from "@/components/autonomous-run-panel";
import { ChatPanel } from "@/components/chat-panel";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
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
import { autonomousResolutionHeadline } from "@/lib/incident-resolution-copy";
import type {
  Artifact,
  FailureCategory,
  IncidentAutonomousRunDetail,
  IncidentPatch,
  IncidentRootCause,
  IncidentSandboxRunDetail,
  IncidentSandboxRun,
  SandboxRunAttempt,
  SandboxRunStep,
} from "@/lib/types";
import { formatTimestamp } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

type IncidentDetailPageProps = {
  params: Promise<{
    incidentId: string;
  }>;
};

export default async function IncidentDetailPage({
  params,
}: IncidentDetailPageProps) {
  const { incidentId } = await params;
  let detail;
  let classification;
  let rootCause: IncidentRootCause;
  let patch: IncidentPatch;
  let sandboxRuns: IncidentSandboxRun[] = [];
  let latestSandboxDetail: IncidentSandboxRunDetail | null = null;
  let latestAutonomousRunDetail: IncidentAutonomousRunDetail | null = null;

  try {
    [detail, classification, rootCause, patch, sandboxRuns] = await Promise.all([
      getIncident(incidentId, { eventLimit: 100 }),
      getIncidentClassification(incidentId, { eventLimit: 50 }),
      getIncidentRootCause(incidentId, { eventLimit: 50 }),
      getIncidentPatch(incidentId, { eventLimit: 50 }),
      listIncidentSandboxRuns(incidentId, { limit: 10 }).catch((caughtError) => {
        if (
          caughtError instanceof AgentPlatformError &&
          caughtError.status === 404
        ) {
          return [];
        }
        throw caughtError;
      }),
    ]);
  } catch (caughtError) {
    if (
      caughtError instanceof AgentPlatformError &&
      caughtError.status === 404
    ) {
      notFound();
    }
    throw caughtError;
  }
  const { incident, events } = detail;

  const sandboxDetailPromise =
    sandboxRuns.length > 0
      ? getIncidentSandboxRunDetail(incidentId, sandboxRuns[0].id).catch(
          (caughtError) => {
            if (
              caughtError instanceof AgentPlatformError &&
              caughtError.status === 404
            ) {
              return null;
            }
            throw caughtError;
          },
        )
      : Promise.resolve(null);

  const autonomousDetailPromise = getLatestIncidentAutonomousRunDetail(
    incidentId,
  ).catch((caughtError) => {
    if (
      caughtError instanceof AgentPlatformError &&
      caughtError.status === 404
    ) {
      return null;
    }
    throw caughtError;
  });

  const [sandboxResolved, autonomousResolved] = await Promise.all([
    sandboxDetailPromise,
    autonomousDetailPromise,
  ]);
  latestSandboxDetail = sandboxResolved;
  latestAutonomousRunDetail = autonomousResolved;

  const primarySignal = events[0]?.error_message?.trim() ?? null;
  const run = latestAutonomousRunDetail?.run;
  const outcome = latestAutonomousRunDetail?.outcome;
  const showLiveStrip =
    incident.status === "open" &&
    run &&
    (run.status === "running" ||
      run.status === "queued" ||
      run.approval_status === "pending");
  const showSolvedHero =
    run?.status === "succeeded" &&
    outcome?.fresh_verification_satisfied &&
    Boolean(run.promotion_url);
  const showFixReadyHero = run?.status === "succeeded" && !showSolvedHero;

  const card = "rounded-xl border border-white/[0.06] bg-[rgba(14,18,28,0.85)]";

  return (
    <main className="mx-auto max-w-[1120px] space-y-5 px-2 pb-14 pt-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/incidents"
          className="text-sm font-medium text-white/50 transition hover:text-white/80"
        >
          ← Incident center
        </Link>
        <span className="text-[11px] text-white/30">ID {incident.id}</span>
      </div>

      <section className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[rgba(14,18,28,0.92)] p-5 sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
              Incident
            </p>
            <h1 className="mt-1 text-2xl font-bold leading-tight text-white sm:text-[1.65rem]">
              {incident.title}
            </h1>
            {primarySignal ? (
              <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-white/60">
                {primarySignal}
              </p>
            ) : (
              <p className="mt-3 text-sm text-white/45">
                No error message on the latest event yet — open evidence below for full context.
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 lg:justify-end">
            <SeverityBadge severity={incident.severity} />
            <StatusBadge status={incident.status} />
            <span className="rounded-full border border-white/10 bg-white/[0.05] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-white/65">
              {incident.environment}
            </span>
            <span className="rounded-full border border-[rgba(255,106,61,0.25)] bg-[rgba(255,106,61,0.08)] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#ffb99a]">
              {incident.service}
            </span>
          </div>
        </div>

        {run?.policy_block_reason ? (
          <div className="mt-4 rounded-xl border border-[rgba(255,178,83,0.35)] bg-[rgba(255,178,83,0.08)] px-4 py-4">
            <p className="text-sm font-semibold text-[#fde68a]">Auto-repair blocked</p>
            <p className="mt-1 text-sm leading-relaxed text-white/70">{run.policy_block_reason}</p>
          </div>
        ) : null}

        {showSolvedHero && run && outcome ? (
          <div className="mt-4 rounded-2xl border border-[rgba(32,201,51,0.28)] bg-[rgba(32,201,51,0.08)] p-4 sm:p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-[#86efac]">
                  Solved
                </p>
                <h2 className="mt-1 text-xl font-semibold text-white">
                  Fix proposed by Stimpact
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-white/70">
                  The agent reproduced the issue, validated a working repair, and opened a pull request with the proposed fix.
                </p>
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-white/50">
                  <span>Verified {formatTimestamp(outcome.completed_at)}</span>
                  {run.promotion_branch_name ? <span>Branch {run.promotion_branch_name}</span> : null}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <a
                  href={run.promotion_url ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-[rgba(32,201,51,0.35)] bg-[rgba(32,201,51,0.14)] px-3.5 py-2 text-sm font-semibold text-[#bbf7d0] transition hover:bg-[rgba(32,201,51,0.2)]"
                >
                  View pull request
                </a>
                <a
                  href="#full-patch"
                  className="rounded-lg border border-white/10 bg-white/[0.05] px-3.5 py-2 text-sm font-medium text-white/75 transition hover:bg-white/[0.08]"
                >
                  Show full patch
                </a>
              </div>
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-xl border border-white/[0.08] bg-black/20 p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                  Root cause
                </p>
                <p className="mt-2 text-sm leading-relaxed text-white/75">
                  {outcome.root_cause_explanation ?? rootCause.reasoning.reasoning_summary}
                </p>
              </div>
              <div className="rounded-xl border border-white/[0.08] bg-black/20 p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                  How it was fixed
                </p>
                <p className="mt-2 text-sm leading-relaxed text-white/75">
                  {outcome.solution_description ?? patch.rationale}
                </p>
              </div>
            </div>
          </div>
        ) : null}

        {showFixReadyHero && run ? (
          <div className="mt-4 rounded-2xl border border-[rgba(45,127,249,0.3)] bg-[rgba(45,127,249,0.08)] p-4 sm:p-5">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[#93c5fd]">
              Fix ready
            </p>
            <h2 className="mt-1 text-xl font-semibold text-white">
              The repair workflow completed successfully
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-white/70">
              Verification passed. {run.promotion_url ? "The PR is ready for review." : "Promotion is the next step to open the PR."}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {run.promotion_url ? (
                <a
                  href={run.promotion_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-[rgba(45,127,249,0.35)] bg-[rgba(45,127,249,0.14)] px-3.5 py-2 text-sm font-semibold text-[#bfdbfe] transition hover:bg-[rgba(45,127,249,0.2)]"
                >
                  View pull request
                </a>
              ) : null}
              <a
                href="#full-patch"
                className="rounded-lg border border-white/10 bg-white/[0.05] px-3.5 py-2 text-sm font-medium text-white/75 transition hover:bg-white/[0.08]"
              >
                Show full patch
              </a>
            </div>
          </div>
        ) : null}

        {showLiveStrip && run ? (
          <div
            className={`mt-5 flex flex-col gap-3 rounded-xl border px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${
              run.approval_status === "pending"
                ? "border-[rgba(255,178,83,0.35)] bg-[rgba(255,178,83,0.08)]"
                : "border-[rgba(255,106,61,0.35)] bg-[rgba(255,106,61,0.08)]"
            }`}
          >
            <div className="flex items-center gap-3">
              {run.approval_status !== "pending" &&
              (run.status === "running" || run.status === "queued") ? (
                <span className="relative flex h-2.5 w-2.5 shrink-0">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#ff6a3d] opacity-60" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#ff6a3d]" />
                </span>
              ) : (
                <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-[#fde68a]" />
              )}
              <p
                className={`text-sm font-medium ${
                  run.approval_status === "pending" ? "text-[#fde68a]" : "text-[#ffb99a]"
                }`}
              >
                {autonomousResolutionHeadline({
                  status: run.status,
                  phase: run.phase,
                  approval_status: run.approval_status,
                  execution_mode: run.execution_mode,
                })}
              </p>
            </div>
            <span className="text-[11px] font-medium uppercase tracking-wider text-white/40">
              Resolution · live
            </span>
          </div>
        ) : null}

        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <DetailStat label="Status" value={incident.status} />
          <DetailStat label="Severity" value={incident.severity} />
          <DetailStat label="Events" value={String(incident.event_count)} />
          <DetailStat
            label="Telemetry"
            value={incident.latest_telemetry_id.slice(0, 14)}
          />
        </div>
      </section>

      <AutonomousRunPanel
        incidentId={incident.id}
        initialDetail={latestAutonomousRunDetail}
        initialSandboxDetail={latestSandboxDetail}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className={`${card} p-5`}>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
            Failure classification
          </p>
          <div className="mt-2 flex items-start justify-between gap-3">
            <h2 className="text-base font-semibold text-white">
              {formatFailureCategory(classification.category)}
            </h2>
            <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white/55">
              {Math.round(classification.confidence * 100)}%
            </span>
          </div>
          <p className="mt-3 line-clamp-4 text-sm leading-relaxed text-white/55">
            {classification.summary}
          </p>
        </div>

        <div className={`${card} p-5`}>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
            Root cause hypothesis
          </p>
          <div className="mt-2 flex items-start justify-between gap-3">
            <h2 className="text-base font-semibold text-white leading-snug">
              {rootCause.reasoning.root_cause_hypothesis}
            </h2>
            <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white/55">
              {Math.round(rootCause.reasoning.confidence * 100)}%
            </span>
          </div>
          <p className="mt-3 line-clamp-4 text-sm leading-relaxed text-white/55">
            {rootCause.reasoning.reasoning_summary}
          </p>
        </div>
      </div>

      <details id="full-patch" className={`group ${card} overflow-hidden`}>
        <summary className="cursor-pointer list-none px-5 py-4 text-left transition hover:bg-white/[0.03] [&::-webkit-details-marker]:hidden">
          <span className="flex items-center justify-between gap-2">
            <span>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                Captured evidence
              </span>
              <span className="ml-2 text-sm font-medium text-white/80">
                {events.length} event{events.length !== 1 ? "s" : ""}
              </span>
            </span>
            <span className="text-white/35 transition group-open:rotate-180">▼</span>
          </span>
        </summary>
        <div className="border-t border-white/[0.06] px-5 pb-5">
          {events.length === 0 ? (
            <p className="pt-4 text-sm text-white/45">No incident events attached yet.</p>
          ) : (
            <div className="space-y-4 pt-4">
              {events.map((event) => (
                <article
                  key={event.id}
                  className="rounded-xl border border-white/[0.06] bg-black/25 px-4 py-4"
                >
                  <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                        {event.event_type}
                      </p>
                      <h3 className="mt-1.5 text-sm font-semibold text-white/95">
                        {event.error_message}
                      </h3>
                      <p className="mt-1 text-xs text-white/40">
                        {event.telemetry_id} · {formatTimestamp(event.occurred_at)}
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 grid gap-3 xl:grid-cols-3">
                    <ContextCard title="Stack trace" content={event.stacktrace} mono />
                    <ContextCard
                      title="Request payload"
                      content={serializeJson(event.request_payload)}
                      mono
                    />
                    <ContextCard
                      title="Response payload"
                      content={serializeJson(event.response_payload)}
                      mono
                    />
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </details>

      <details className={`group ${card} overflow-hidden`}>
        <summary className="cursor-pointer list-none px-5 py-4 text-left transition hover:bg-white/[0.03] [&::-webkit-details-marker]:hidden">
          <span className="flex items-center justify-between gap-2">
            <span>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                AI patch
              </span>
              <span className="ml-2 line-clamp-1 text-sm font-medium text-white/80">
                {patch.patch_summary}
              </span>
            </span>
            <span className="text-white/35 transition group-open:rotate-180">▼</span>
          </span>
        </summary>
        <div className="border-t border-white/[0.06] px-5 pb-5 pt-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm leading-relaxed text-white/60">{patch.rationale}</p>
            {patch.status === "failed" ? (
              <span className="shrink-0 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-200">
                No diff
              </span>
            ) : (
              <span className="shrink-0 rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-white/50">
                {Math.round(patch.confidence * 100)}% conf.
              </span>
            )}
          </div>
          <div className="mt-4 grid gap-0 rounded-lg border border-white/[0.06] bg-black/20">
            <RootCauseRow label="Files changed" value={String(patch.file_count)} />
            <RootCauseRow label="Diff lines" value={String(patch.diff_line_count)} />
            <RootCauseRow label="Patch model" value={patch.model_name} />
          </div>
          {patch.target_files.length > 0 ? (
            <div className="mt-4 space-y-2">
              {patch.target_files.map((target) => (
                <div
                  key={target.path}
                  className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-3"
                >
                  <p className="text-sm font-medium text-white/90">{target.path}</p>
                  <p className="mt-1 text-sm text-white/50">{target.reason}</p>
                </div>
              ))}
            </div>
          ) : null}
          {patch.verification_steps.length > 0 ? (
            <div className="mt-4">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                Suggested verification
              </p>
              <ul className="mt-2 space-y-1.5 text-sm text-white/55">
                {patch.verification_steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-4 rounded-lg border border-white/[0.06] bg-black/30 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
              Unified diff
            </p>
            {patch.status === "failed" || !patch.unified_diff.trim() ? (
              <p className="mt-3 text-sm text-white/45">
                No unified diff was produced for this incident.
              </p>
            ) : (
              <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-[#a5d4ff]">
                {patch.unified_diff}
              </pre>
            )}
          </div>
        </div>
      </details>

      <details className={`group ${card} overflow-hidden`}>
        <summary className="cursor-pointer list-none px-5 py-4 text-left transition hover:bg-white/[0.03] [&::-webkit-details-marker]:hidden">
          <span className="flex items-center justify-between gap-2">
            <span>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                Sandbox verification
              </span>
              <span className="ml-2 text-sm font-medium text-white/80">
                {latestSandboxDetail ? latestSandboxDetail.run.summary : "No runs yet"}
              </span>
            </span>
            <span className="text-white/35 transition group-open:rotate-180">▼</span>
          </span>
        </summary>
        <div className="border-t border-white/[0.06] px-5 pb-5 pt-4">
          {latestSandboxDetail ? (
            <>
              <div className="mb-4 flex items-center justify-between">
                <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-white/55">
                  {latestSandboxDetail.run.status}
                </span>
              </div>
              <div className="grid gap-0 rounded-lg border border-white/[0.06] bg-black/20">
                <RootCauseRow
                  label="Failure reproduced"
                  value={latestSandboxDetail.run.reproduction_succeeded ? "Yes" : "No"}
                />
                <RootCauseRow
                  label="Patch applied"
                  value={latestSandboxDetail.run.patch_applied ? "Yes" : "No"}
                />
                <RootCauseRow
                  label="Verification passed"
                  value={latestSandboxDetail.run.verification_succeeded ? "Yes" : "No"}
                />
                <RootCauseRow label="Executor" value={latestSandboxDetail.run.executor_backend} />
              </div>
              {sandboxRuns.length > 0 ? (
                <div className="mt-4 space-y-2">
                  {sandboxRuns.map((run) => (
                    <div
                      key={run.id}
                      className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-3"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="text-sm font-medium text-white/90">{run.summary}</p>
                          <p className="mt-1 text-xs text-white/45">{formatTimestamp(run.created_at)}</p>
                        </div>
                        <span className="text-[10px] font-semibold uppercase text-white/45">
                          {run.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {latestSandboxDetail.steps.length > 0 ? (
                <div className="mt-4">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                    Run steps
                  </p>
                  <div className="mt-2 space-y-2">
                    {latestSandboxDetail.steps.map((step) => (
                      <SandboxStepCard key={step.id} step={step} />
                    ))}
                  </div>
                </div>
              ) : null}
              {latestSandboxDetail.attempts.length > 0 ? (
                <div className="mt-4">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                    Attempts
                  </p>
                  <div className="mt-2 space-y-2">
                    {latestSandboxDetail.attempts.map((attempt) => (
                      <SandboxAttemptCard key={attempt.id} attempt={attempt} />
                    ))}
                  </div>
                </div>
              ) : null}
              {latestSandboxDetail.artifacts.length > 0 ? (
                <div className="mt-4">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                    Artifacts
                  </p>
                  <div className="mt-2 space-y-2">
                    {latestSandboxDetail.artifacts.map((artifact) => (
                      <SandboxArtifactCard key={artifact.id} artifact={artifact} />
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="mt-4 rounded-lg border border-white/[0.06] bg-black/30 p-4">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                  Execution log
                </p>
                <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-white/65">
                  {latestSandboxDetail.run.execution_log ||
                    "Execution log stored via artifacts or pending external completion."}
                </pre>
              </div>
            </>
          ) : (
            <p className="text-sm text-white/45">
              No sandbox runs have been queued yet. Configure a repo profile and queue via the sandbox API when ready.
            </p>
          )}
        </div>
      </details>

      <details className={`group ${card} overflow-hidden`}>
        <summary className="cursor-pointer list-none px-5 py-4 text-left transition hover:bg-white/[0.03] [&::-webkit-details-marker]:hidden">
          <span className="flex items-center justify-between gap-2">
            <span>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                Grounding & signals
              </span>
              <span className="ml-2 text-sm font-medium text-white/80">Evidence bundle</span>
            </span>
            <span className="text-white/35 transition group-open:rotate-180">▼</span>
          </span>
        </summary>
        <div className="border-t border-white/[0.06] px-5 pb-5 pt-4">
          <p className="text-sm leading-relaxed text-white/55">{rootCause.evidence.evidence_summary}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {rootCause.evidence.stack_trace_signals.map((signal) => (
              <span
                key={signal}
                className="rounded-full border border-white/10 bg-white/[0.05] px-2.5 py-1 text-[11px] font-medium text-white/65"
              >
                {signal}
              </span>
            ))}
          </div>
          <div className="mt-4 grid gap-0 rounded-lg border border-white/[0.06] bg-black/20">
            <RootCauseRow
              label="Suspected component"
              value={rootCause.evidence.suspected_component ?? "No strong file candidate yet"}
            />
            <RootCauseRow
              label="Evidence confidence"
              value={`${Math.round(rootCause.evidence.evidence_confidence * 100)}%`}
            />
            <RootCauseRow
              label="Latest commit SHA"
              value={rootCause.evidence.latest_commit_sha ?? "Unavailable"}
            />
          </div>
          {rootCause.evidence.code_candidates.length > 0 ? (
            <div className="mt-4 space-y-2">
              {rootCause.evidence.code_candidates.map((candidate) => (
                <div
                  key={`${candidate.file_path}-${candidate.symbol ?? "none"}`}
                  className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-3"
                >
                  <p className="text-sm font-medium text-white/90">{candidate.file_path}</p>
                  <p className="mt-1 text-sm text-white/50">{candidate.match_reason}</p>
                  <p className="mt-2 text-[10px] font-semibold uppercase text-white/35">
                    {Math.round(candidate.confidence * 100)}% match
                  </p>
                </div>
              ))}
            </div>
          ) : null}
          {rootCause.evidence.code_snippets.length > 0 ? (
            <div className="mt-4 space-y-3">
              {rootCause.evidence.code_snippets.map((snippet) => (
                <div
                  key={`${snippet.file_path}-${snippet.start_line}-${snippet.end_line}`}
                  className="rounded-lg border border-white/[0.06] bg-black/25 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-white/90">{snippet.file_path}</p>
                      <p className="mt-1 text-xs text-white/45">{snippet.match_reason}</p>
                    </div>
                    <span className="text-[10px] font-semibold uppercase text-white/35">
                      {Math.round(snippet.confidence * 100)}% match
                    </span>
                  </div>
                  <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-white/[0.03] p-3 font-mono text-xs leading-relaxed text-[#a5d4ff]">
                    {snippet.content}
                  </pre>
                </div>
              ))}
            </div>
          ) : null}
          {rootCause.evidence.git_signals.length > 0 ? (
            <div className="mt-4 space-y-2">
              {rootCause.evidence.git_signals.map((signal) => (
                <div
                  key={`${signal.file_path}-${signal.commit_sha}`}
                  className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-3"
                >
                  <p className="text-sm font-medium text-white/90">{signal.commit_summary}</p>
                  <p className="mt-1 text-sm text-white/50">{signal.file_path}</p>
                  <p className="mt-2 text-[10px] font-semibold uppercase text-white/35">
                    {signal.commit_sha.slice(0, 12)}
                  </p>
                </div>
              ))}
            </div>
          ) : null}
          {rootCause.reasoning.alternative_hypotheses.length > 0 ? (
            <div className="mt-4">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                Alternative hypotheses
              </p>
              <ul className="mt-2 space-y-1.5 text-sm text-white/55">
                {rootCause.reasoning.alternative_hypotheses.map((hypothesis) => (
                  <li key={hypothesis}>{hypothesis}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </details>

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

function DetailStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-black/25 px-3 py-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-white/35">{label}</p>
      <p className="mt-1 break-all text-sm font-medium text-white/90">{value}</p>
    </div>
  );
}

function ContextCard({
  title,
  content,
  mono = false,
}: {
  title: string;
  content: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-black/35 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">{title}</p>
      <pre
        className={`mt-2 max-h-80 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-[#a5d4ff] ${
          mono ? "font-mono" : ""
        }`}
      >
        {content}
      </pre>
    </div>
  );
}

function SandboxStepCard({ step }: { step: SandboxRunStep }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-white/90">{step.step_name}</p>
          <p className="mt-1 text-sm text-white/50">{step.summary}</p>
        </div>
        <span className="text-[10px] font-semibold uppercase text-white/45">{step.status}</span>
      </div>
    </div>
  );
}

function SandboxAttemptCard({ attempt }: { attempt: SandboxRunAttempt }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-white/90">Attempt {attempt.attempt_number}</p>
          <p className="mt-1 text-sm text-white/50">{attempt.error_message ?? "No recorded error."}</p>
        </div>
        <span className="text-[10px] font-semibold uppercase text-white/45">{attempt.status}</span>
      </div>
    </div>
  );
}

function SandboxArtifactCard({ artifact }: { artifact: Artifact }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-3">
      <p className="text-sm font-medium text-white/90">{artifact.artifact_type}</p>
      <p className="mt-1 break-all text-sm text-white/50">{artifact.uri}</p>
      <p className="mt-2 text-[10px] font-semibold uppercase text-white/35">{artifact.storage_backend}</p>
    </div>
  );
}

function serializeJson(value: unknown): string {
  if (value === null || value === undefined) {
    return "null";
  }

  if (typeof value === "string") {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatFailureCategory(category: FailureCategory): string {
  return category
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function RootCauseRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/[0.06] px-3 py-2.5 last:border-b-0">
      <span className="text-sm text-white/45">{label}</span>
      <span className="break-all text-right text-sm font-medium text-white/85">{value}</span>
    </div>
  );
}
