import Link from "next/link";
import { notFound } from "next/navigation";

import { ChatPanel } from "@/components/chat-panel";
import { PageHeader, PreviewNotice, SectionCard } from "@/components/dashboard-ui";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import {
  AgentPlatformError,
  getIncident,
  getIncidentClassification,
  getIncidentPatch,
  getIncidentRootCause,
  getIncidentSandboxRunDetail,
  listIncidentSandboxRuns,
} from "@/lib/agent-platform";
import type {
  Artifact,
  FailureCategory,
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

  if (sandboxRuns.length > 0) {
    try {
      latestSandboxDetail = await getIncidentSandboxRunDetail(
        incidentId,
        sandboxRuns[0].id,
      );
    } catch (caughtError) {
      if (
        !(caughtError instanceof AgentPlatformError) ||
        caughtError.status !== 404
      ) {
        throw caughtError;
      }
    }
  }

  return (
    <main className="space-y-6">
      <PageHeader
        eyebrow="Incident detail"
        title={incident.title}
        description={`Project ${incident.project_id} in ${incident.environment}. Use this view for evidence review, detailed event context, and incident-specific AI analysis.`}
        action={
          <Link
            href="/incidents"
            className="vault-button-secondary inline-flex items-center rounded-2xl border border-[rgba(111,158,210,0.2)] px-4 py-2.5 text-sm font-semibold text-[#35547d] transition"
          >
            Back to incident center
          </Link>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <DetailStat label="Status" value={incident.status} />
        <DetailStat label="Severity" value={incident.severity} />
        <DetailStat label="Events" value={String(incident.event_count)} />
        <DetailStat label="Latest telemetry" value={incident.latest_telemetry_id.slice(0, 14)} />
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={incident.severity} />
        <StatusBadge status={incident.status} />
        <span className="rounded-full bg-[#f4f8fd] px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[#5d7898]">
          {incident.environment}
        </span>
        <span className="rounded-full bg-[#fff8db] px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[#876600]">
          {incident.service}
        </span>
        <span className="text-sm text-[#6480a0]">Incident ID {incident.id}</span>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_360px]">
        <section className="space-y-4">
          <SectionCard
            title="Captured evidence"
            description="Timeline entries and runtime payloads attached to this incident."
          >
            {events.length === 0 ? (
              <div className="vault-empty rounded-[28px] px-6 py-10 text-sm text-[#58708e] shadow-sm">
                No incident events have been attached yet.
              </div>
            ) : (
              <div className="space-y-4">
                {events.map((event) => (
                  <article
                    key={event.id}
                    className="rounded-[24px] border border-[rgba(111,158,210,0.14)] bg-white px-5 py-5"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <p className="vault-section-title text-[11px] font-semibold uppercase">
                          {event.event_type}
                        </p>
                        <h3 className="mt-2 text-base font-semibold text-[#17385d]">
                          {event.error_message}
                        </h3>
                        <p className="mt-1 text-sm text-[#5d7391]">
                          Telemetry {event.telemetry_id} • {formatTimestamp(event.occurred_at)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-4 xl:grid-cols-3">
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
          </SectionCard>

          <ChatPanel
            title="Incident detail chat"
            description="Ask grounded questions about this incident, its event history, stack traces, and captured request or response data."
            endpoint={`/api/incidents/${incident.id}/chat`}
            extraBody={{
              event_limit: 50,
            }}
            suggestedPrompts={[
              "Summarize the likely root problem in this incident.",
              "What evidence from the recent events is most important?",
              "What debugging steps should an engineer take next for this incident?",
            ]}
          />
        </section>

        <div className="space-y-6">
          <section className="ops-sheet-muted rounded-[22px] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="ops-kicker text-[11px] font-semibold uppercase">
                  Failure classification
                </p>
                <h3 className="mt-3 text-base font-semibold text-[#171717]">
                  {formatFailureCategory(classification.category)}
                </h3>
              </div>
              <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#745744]">
                {Math.round(classification.confidence * 100)}% confidence
              </span>
            </div>
            <p className="mt-4 text-sm leading-6 text-[#746d66]">
              {classification.summary}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {classification.matched_signals.map((signal) => (
                <span
                  key={signal}
                  className="rounded-full bg-white/70 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[#5d7898]"
                >
                  {signal}
                </span>
              ))}
            </div>
          </section>

          <section className="ops-sheet rounded-[22px] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="ops-kicker text-[11px] font-semibold uppercase">
                  AI root cause hypothesis
                </p>
                <h3 className="mt-3 text-base font-semibold text-[#171717]">
                  {rootCause.reasoning.root_cause_hypothesis}
                </h3>
              </div>
              <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#745744]">
                {Math.round(rootCause.reasoning.confidence * 100)}% confidence
              </span>
            </div>
            <p className="mt-4 text-sm leading-6 text-[#746d66]">
              {rootCause.reasoning.reasoning_summary}
            </p>
            <div className="mt-4 grid gap-4">
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
            {rootCause.reasoning.alternative_hypotheses.length > 0 ? (
              <div className="mt-5">
                <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                  Alternative hypotheses
                </p>
                <ul className="mt-3 space-y-2 text-sm leading-6 text-[#5f6470]">
                  {rootCause.reasoning.alternative_hypotheses.map((hypothesis) => (
                    <li key={hypothesis}>{hypothesis}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          <section className="ops-sheet-muted rounded-[22px] p-5">
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Grounding evidence
            </p>
            <p className="mt-3 text-sm leading-6 text-[#746d66]">
              {rootCause.evidence.evidence_summary}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {rootCause.evidence.stack_trace_signals.map((signal) => (
                <span
                  key={signal}
                  className="rounded-full bg-white/70 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[#5d7898]"
                >
                  {signal}
                </span>
              ))}
            </div>
            {rootCause.evidence.code_candidates.length > 0 ? (
              <div className="mt-5 space-y-3">
                {rootCause.evidence.code_candidates.map((candidate) => (
                  <div
                    key={`${candidate.file_path}-${candidate.symbol ?? "none"}`}
                    className="rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 px-4 py-4"
                  >
                    <p className="text-sm font-semibold text-[#17385d]">
                      {candidate.file_path}
                    </p>
                    <p className="mt-1 text-sm text-[#5f6470]">
                      {candidate.match_reason}
                    </p>
                    <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                      {Math.round(candidate.confidence * 100)}% match
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
            {rootCause.evidence.git_signals.length > 0 ? (
              <div className="mt-5 space-y-3">
                {rootCause.evidence.git_signals.map((signal) => (
                  <div
                    key={`${signal.file_path}-${signal.commit_sha}`}
                    className="rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 px-4 py-4"
                  >
                    <p className="text-sm font-semibold text-[#17385d]">
                      {signal.commit_summary}
                    </p>
                    <p className="mt-1 text-sm text-[#5f6470]">{signal.file_path}</p>
                    <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                      {signal.commit_sha.slice(0, 12)}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          <section className="ops-sheet rounded-[22px] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="ops-kicker text-[11px] font-semibold uppercase">
                  AI patch recommendation
                </p>
                <h3 className="mt-3 text-base font-semibold text-[#171717]">
                  {patch.patch_summary}
                </h3>
              </div>
              <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#745744]">
                {Math.round(patch.confidence * 100)}% confidence
              </span>
            </div>
            <p className="mt-4 text-sm leading-6 text-[#746d66]">
              {patch.rationale}
            </p>
            <div className="mt-4 grid gap-4">
              <RootCauseRow label="Files changed" value={String(patch.file_count)} />
              <RootCauseRow label="Diff lines" value={String(patch.diff_line_count)} />
              <RootCauseRow label="Patch model" value={patch.model_name} />
            </div>
            {patch.target_files.length > 0 ? (
              <div className="mt-5 space-y-3">
                {patch.target_files.map((target) => (
                  <div
                    key={target.path}
                    className="rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 px-4 py-4"
                  >
                    <p className="text-sm font-semibold text-[#17385d]">{target.path}</p>
                    <p className="mt-1 text-sm text-[#5f6470]">{target.reason}</p>
                  </div>
                ))}
              </div>
            ) : null}
            {patch.verification_steps.length > 0 ? (
              <div className="mt-5">
                <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                  Suggested verification
                </p>
                <ul className="mt-3 space-y-2 text-sm leading-6 text-[#5f6470]">
                  {patch.verification_steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="mt-5 rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                Unified diff
              </p>
              <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-sm leading-6 text-[#35547d]">
                {patch.unified_diff}
              </pre>
            </div>
          </section>

          <section className="ops-sheet-muted rounded-[22px] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="ops-kicker text-[11px] font-semibold uppercase">
                  Sandbox verification
                </p>
                <h3 className="mt-3 text-base font-semibold text-[#171717]">
                  {latestSandboxDetail
                    ? latestSandboxDetail.run.summary
                    : "No sandbox verification runs yet"}
                </h3>
              </div>
              {latestSandboxDetail ? (
                <span className="rounded-full bg-[rgba(23,23,23,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#745744]">
                  {latestSandboxDetail.run.status}
                </span>
              ) : null}
            </div>
            {latestSandboxDetail ? (
              <>
                <div className="mt-4 grid gap-4">
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
                  <RootCauseRow
                    label="Executor"
                    value={latestSandboxDetail.run.executor_backend}
                  />
                </div>
                {sandboxRuns.length > 0 ? (
                  <div className="mt-5 space-y-3">
                    {sandboxRuns.map((run) => (
                      <div
                        key={run.id}
                        className="rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 px-4 py-4"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-sm font-semibold text-[#17385d]">
                              {run.summary}
                            </p>
                            <p className="mt-1 text-sm text-[#5f6470]">
                              {formatTimestamp(run.created_at)}
                            </p>
                          </div>
                          <span className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                            {run.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
                {latestSandboxDetail.steps.length > 0 ? (
                  <div className="mt-5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                      Run steps
                    </p>
                    <div className="mt-3 space-y-3">
                      {latestSandboxDetail.steps.map((step) => (
                        <SandboxStepCard key={step.id} step={step} />
                      ))}
                    </div>
                  </div>
                ) : null}
                {latestSandboxDetail.attempts.length > 0 ? (
                  <div className="mt-5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                      Attempts
                    </p>
                    <div className="mt-3 space-y-3">
                      {latestSandboxDetail.attempts.map((attempt) => (
                        <SandboxAttemptCard key={attempt.id} attempt={attempt} />
                      ))}
                    </div>
                  </div>
                ) : null}
                {latestSandboxDetail.artifacts.length > 0 ? (
                  <div className="mt-5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                      Artifacts
                    </p>
                    <div className="mt-3 space-y-3">
                      {latestSandboxDetail.artifacts.map((artifact) => (
                        <SandboxArtifactCard key={artifact.id} artifact={artifact} />
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="mt-5 rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
                    Execution log
                  </p>
                  <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-sm leading-6 text-[#35547d]">
                    {latestSandboxDetail.run.execution_log || "Execution log stored via artifacts or pending external completion."}
                  </pre>
                </div>
              </>
            ) : (
              <p className="mt-4 text-sm leading-6 text-[#746d66]">
                No sandbox runs have been queued yet. Queue one through the
                sandbox run API after configuring a repo profile for this
                project. Production runs now track asynchronous state, steps,
                and artifacts rather than only a single inline verification
                result.
              </p>
            )}
          </section>

          <PreviewNotice
            title="Detail-page features still to be connected"
            items={[
              "Deploy correlation, assignee ownership, and linked change requests are not wired yet.",
              "PR and merge-request automation will appear after provider write integration and deployment workflow are added.",
            ]}
          />
        </div>
      </div>
    </main>
  );
}

function DetailStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="vault-stat-card rounded-[24px] px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-[#6a83a2]">
        {label}
      </p>
      <p className="mt-2 break-all text-sm font-medium text-[#17385d]">
        {value}
      </p>
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
    <div className="vault-code rounded-2xl p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
        {title}
      </p>
      <pre
        className={`mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-sm leading-6 text-[#35547d] ${
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
    <div className="rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 px-4 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-[#17385d]">{step.step_name}</p>
          <p className="mt-1 text-sm text-[#5f6470]">{step.summary}</p>
        </div>
        <span className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
          {step.status}
        </span>
      </div>
    </div>
  );
}

function SandboxAttemptCard({ attempt }: { attempt: SandboxRunAttempt }) {
  return (
    <div className="rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 px-4 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-[#17385d]">
            Attempt {attempt.attempt_number}
          </p>
          <p className="mt-1 text-sm text-[#5f6470]">
            {attempt.error_message ?? "No recorded error."}
          </p>
        </div>
        <span className="text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
          {attempt.status}
        </span>
      </div>
    </div>
  );
}

function SandboxArtifactCard({ artifact }: { artifact: Artifact }) {
  return (
    <div className="rounded-2xl border border-[rgba(111,158,210,0.14)] bg-white/70 px-4 py-4">
      <p className="text-sm font-semibold text-[#17385d]">{artifact.artifact_type}</p>
      <p className="mt-1 break-all text-sm text-[#5f6470]">{artifact.uri}</p>
      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-[#6380a3]">
        {artifact.storage_backend}
      </p>
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
    <div className="flex items-center justify-between gap-4 border-b border-[rgba(24,24,27,0.08)] py-3 last:border-b-0">
      <span className="text-sm text-[#667085]">{label}</span>
      <span className="break-all text-sm font-semibold text-[#111827]">{value}</span>
    </div>
  );
}
