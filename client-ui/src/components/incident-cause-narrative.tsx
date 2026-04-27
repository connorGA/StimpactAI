import Link from "next/link";

import { IncidentStatusActions } from "@/components/incident-status-actions";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { autonomousResolutionHeadline } from "@/lib/incident-resolution-copy";
import { formatTimestamp } from "@/lib/dashboard";
import type {
  FailureCategory,
  IncidentAutonomousRunDetail,
  IncidentRootCause,
  IncidentSummary,
} from "@/lib/types";

type CauseNarrativeProps = {
  incident: IncidentSummary;
  primarySignal: string | null;
  classification: { category: FailureCategory; summary: string; confidence: number };
  rootCause: IncidentRootCause;
  rootCauseNarrative: string;
  whatWasWrong: string;
  theFix: string;
  latestAutonomousRunDetail: IncidentAutonomousRunDetail | null;
  showSolvedStrip: boolean;
  showFixReadyStrip: boolean;
  showLiveStrip: boolean;
};

function formatCategory(category: FailureCategory): string {
  return category
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function IncidentCauseNarrative({
  incident,
  primarySignal,
  classification,
  rootCause,
  rootCauseNarrative,
  whatWasWrong,
  theFix,
  latestAutonomousRunDetail,
  showSolvedStrip,
  showFixReadyStrip,
  showLiveStrip,
}: CauseNarrativeProps) {
  const run = latestAutonomousRunDetail?.run;
  const outcome = latestAutonomousRunDetail?.outcome;
  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <Link
          href="/incidents"
          className="font-medium text-white/50 transition hover:text-white/80"
        >
          ← Incident center
        </Link>
        <span className="text-[11px] text-white/30">ID {incident.id}</span>
      </div>

      <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-[rgba(12,16,24,0.95)] p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">Incident</p>
            <h1 className="mt-1.5 text-2xl font-bold leading-tight text-white sm:text-[1.65rem]">
              {incident.title}
            </h1>
            {primarySignal ? (
              <p className="mt-3 line-clamp-4 text-sm leading-relaxed text-white/55">Signal: {primarySignal}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
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
        <div className="mt-4">
          <IncidentStatusActions incidentId={incident.id} status={incident.status} />
        </div>
        {run?.policy_block_reason ? (
          <div className="mt-4 rounded-xl border border-[rgba(255,178,83,0.35)] bg-[rgba(255,178,83,0.08)] px-4 py-4">
            <p className="text-sm font-semibold text-[#fde68a]">Auto-repair blocked</p>
            <p className="mt-1 text-sm leading-relaxed text-white/70">{run.policy_block_reason}</p>
          </div>
        ) : null}
        {showSolvedStrip && run && outcome ? (
          <div className="mt-4 flex flex-col gap-3 rounded-xl border border-[rgba(32,201,51,0.32)] bg-[rgba(32,201,51,0.1)] p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-[#bbf7d0]">
              Fix proposed and PR opened. Verified {formatTimestamp(outcome.completed_at)}
              {run.promotion_branch_name ? ` · ${run.promotion_branch_name}` : ""}
            </p>
            {run.promotion_url ? (
              <a
                href={run.promotion_url}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 rounded-lg border border-[rgba(32,201,51,0.4)] bg-[rgba(32,201,51,0.12)] px-3 py-2 text-sm font-semibold text-[#dcfce7] transition hover:bg-[rgba(32,201,51,0.2)]"
              >
                View pull request
              </a>
            ) : null}
          </div>
        ) : null}
        {showFixReadyStrip && run ? (
          <div className="mt-4 rounded-xl border border-[rgba(45,127,249,0.3)] bg-[rgba(45,127,249,0.1)] px-4 py-3 text-sm text-[#c4d4ff]">
            {run.promotion_url
              ? "Verification passed. The PR is ready for review."
              : "Verification passed. Promotion is the next step to open the PR."}
            {run.promotion_url ? (
              <a
                href={run.promotion_url}
                target="_blank"
                rel="noreferrer"
                className="ml-2 font-semibold text-white underline decoration-white/30 underline-offset-2"
              >
                Open PR
              </a>
            ) : null}
          </div>
        ) : null}
        {showLiveStrip && run ? (
          <div
            className={`mt-4 flex flex-col gap-2 rounded-xl border px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${
              run.approval_status === "pending"
                ? "border-[rgba(255,178,83,0.35)] bg-[rgba(255,178,83,0.08)]"
                : "border-[rgba(255,106,61,0.35)] bg-[rgba(255,106,61,0.08)]"
            }`}
          >
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
            <span className="text-[10px] font-semibold uppercase tracking-wider text-white/35">Live run</span>
          </div>
        ) : null}
      </div>

      <div className="rounded-2xl border border-white/[0.1] bg-[linear-gradient(180deg,rgba(20,24,32,0.85),rgba(8,10,16,0.92))] p-5 sm:p-6">
        <div className="space-y-8">
          <article>
            <h3 className="text-base font-semibold text-[#ff8c5a]">What this was</h3>
            <p className="mt-2 text-sm leading-relaxed text-white/60">
              Classified as <span className="font-medium text-white/80">{formatCategory(classification.category)}</span>
              {classification.confidence > 0 ? (
                <span> ({Math.round(classification.confidence * 100)}% confidence)</span>
              ) : null}
            </p>
            <p className="mt-3 whitespace-pre-line text-[15px] leading-relaxed text-white/80">
              {whatWasWrong}
            </p>
            {rootCause.evidence?.evidence_summary ? (
              <p className="mt-3 text-sm leading-relaxed text-white/50">{rootCause.evidence.evidence_summary}</p>
            ) : null}
          </article>

          <div className="h-px w-full bg-white/[0.08]" aria-hidden />

          <article>
            <h3 className="text-base font-semibold text-[#ff8c5a]">Root cause</h3>
            <p className="mt-3 text-[15px] leading-relaxed text-white/90">{rootCauseNarrative}</p>
            <p className="mt-2 text-xs text-white/40">
              Model confidence: {Math.round(rootCause.reasoning.confidence * 100)}% · from incident evidence and code
              context
            </p>
          </article>

          <div className="h-px w-full bg-white/[0.08]" aria-hidden />

          <article>
            <h3 className="text-base font-semibold text-[#ff8c5a]">The fix</h3>
            <p className="mt-3 text-[15px] leading-relaxed text-white/85">{theFix}</p>
            {run?.promotion_url ? (
              <div className="mt-4 flex flex-wrap gap-2">
                <a
                  href={run.promotion_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-white/12 bg-white/[0.06] px-3 py-1.5 text-sm font-medium text-white/90 transition hover:bg-white/[0.1]"
                >
                  View change request / PR
                </a>
                <a
                  href="#code-changes"
                  className="rounded-lg border border-[#ff6a3d]/30 bg-[#ff6a3d]/10 px-3 py-1.5 text-sm font-medium text-[#ffb99a] transition hover:bg-[#ff6a3d]/20"
                >
                  Jump to code
                </a>
              </div>
            ) : (
              <a
                href="#code-changes"
                className="mt-4 inline-flex rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm font-medium text-white/80 transition hover:bg-white/[0.08]"
              >
                See proposed code below
              </a>
            )}
          </article>
        </div>
      </div>
    </section>
  );
}
