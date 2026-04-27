import type {
  Artifact,
  FailureCategory,
  IncidentEvent,
  IncidentPatch,
  IncidentRootCause,
  IncidentSandboxRun,
  IncidentSandboxRunDetail,
  SandboxRunAttempt,
  SandboxRunStep,
} from "@/lib/types";
import { formatTimestamp } from "@/lib/dashboard";

type TechnicalDetailsProps = {
  events: IncidentEvent[];
  classification: { category: FailureCategory; confidence: number; summary: string };
  rootCause: IncidentRootCause;
  patch: IncidentPatch;
  sandboxRuns: IncidentSandboxRun[];
  latestSandboxDetail: IncidentSandboxRunDetail | null;
};

export function IncidentDetailTechnicalDetails({
  events,
  classification,
  rootCause,
  patch,
  latestSandboxDetail,
  sandboxRuns,
}: TechnicalDetailsProps) {
  return (
    <details className="group overflow-hidden rounded-2xl border border-white/[0.08] bg-[rgba(12,16,24,0.6)] open:border-white/[0.12]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-left transition hover:bg-white/[0.04] [&::-webkit-details-marker]:hidden">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">Technical details</p>
          <p className="mt-0.5 text-sm text-white/60">
            Classification, event evidence, patch metadata, sandbox, and model grounding.
          </p>
        </div>
        <span className="text-white/30 transition group-open:rotate-180" aria-hidden>
          ▼
        </span>
      </summary>
      <div className="space-y-6 border-t border-white/[0.06] px-5 py-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">Failure classification</p>
            <p className="mt-1 text-base font-semibold text-white">
              {formatFailureCategory(classification.category)}
            </p>
            <p className="mt-1 text-sm text-white/50">{Math.round(classification.confidence * 100)}% confidence</p>
            <p className="mt-2 text-sm leading-relaxed text-white/55">{classification.summary}</p>
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">Root cause (model)</p>
            <p className="mt-1 text-base font-semibold leading-snug text-white">
              {rootCause.reasoning.root_cause_hypothesis}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-white/55">
              {rootCause.reasoning.reasoning_summary}
            </p>
            {rootCause.reasoning.alternative_hypotheses.length > 0 ? (
              <ul className="mt-2 list-disc pl-4 text-sm text-white/45">
                {rootCause.reasoning.alternative_hypotheses.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-white/80">Telemetry &amp; event evidence</h3>
          <p className="mt-1 text-xs text-white/40">
            {events.length} event{events.length !== 1 ? "s" : ""} grouped into this incident
          </p>
          <div className="mt-3 space-y-3">
            {events.length === 0 ? (
              <p className="text-sm text-white/45">No events attached.</p>
            ) : (
              events.map((event) => (
                <article
                  key={event.id}
                  className="rounded-xl border border-white/[0.06] bg-black/30 px-4 py-4"
                >
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                    {event.event_type}
                  </p>
                  <h4 className="mt-1.5 text-sm font-semibold text-white/95">{event.error_message}</h4>
                  <p className="mt-1 text-xs text-white/40">
                    {event.telemetry_id} · {formatTimestamp(event.occurred_at)}
                  </p>
                  <div className="mt-3 grid gap-3 xl:grid-cols-3">
                    <ContextCard title="Stack trace" content={event.stacktrace} />
                    <ContextCard title="Request" content={serializeJson(event.request_payload)} />
                    <ContextCard title="Response" content={serializeJson(event.response_payload)} />
                  </div>
                </article>
              ))
            )}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-white/80">Patch record</h3>
          <p className="mt-1 text-sm text-white/50">{patch.patch_summary}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-white/45">
            <span>Files: {patch.file_count}</span>
            <span>·</span>
            <span>Lines: {patch.diff_line_count}</span>
            <span>·</span>
            <span>Model: {patch.model_name}</span>
            {patch.status === "failed" ? (
              <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-amber-200">
                Patch failed
              </span>
            ) : null}
          </div>
          {patch.target_files.length > 0 ? (
            <ul className="mt-3 space-y-1.5 text-sm text-white/60">
              {patch.target_files.map((f) => (
                <li key={f.path}>
                  <code className="text-[#93c5fd]">{f.path}</code> — {f.reason}
                </li>
              ))}
            </ul>
          ) : null}
          {patch.verification_steps.length > 0 ? (
            <div className="mt-3">
              <p className="text-[10px] font-semibold uppercase text-white/40">Suggested verification</p>
              <ol className="mt-1.5 list-decimal pl-4 text-sm text-white/50">
                {patch.verification_steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>

        <div>
          <h3 className="text-sm font-semibold text-white/80">Sandbox</h3>
          {latestSandboxDetail ? (
            <>
              <p className="mt-1 text-sm text-white/60">{latestSandboxDetail.run.summary}</p>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <MetaChip label="Status" value={latestSandboxDetail.run.status} />
                <MetaChip
                  label="Reproduced"
                  value={latestSandboxDetail.run.reproduction_succeeded ? "Yes" : "No"}
                />
                <MetaChip
                  label="Patch applied"
                  value={latestSandboxDetail.run.patch_applied ? "Yes" : "No"}
                />
                <MetaChip
                  label="Verified"
                  value={latestSandboxDetail.run.verification_succeeded ? "Yes" : "No"}
                />
              </div>
              {sandboxRuns.length > 1 ? (
                <ul className="mt-2 space-y-1 text-xs text-white/40">
                  {sandboxRuns.map((r) => (
                    <li key={r.id}>
                      {r.status} — {r.summary} ({formatTimestamp(r.created_at)})
                    </li>
                  ))}
                </ul>
              ) : null}
              {latestSandboxDetail.steps.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {latestSandboxDetail.steps.map((s) => (
                    <SandboxStepCard key={s.id} step={s} />
                  ))}
                </div>
              ) : null}
              {latestSandboxDetail.attempts.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {latestSandboxDetail.attempts.map((a) => (
                    <SandboxAttemptCard key={a.id} attempt={a} />
                  ))}
                </div>
              ) : null}
              {latestSandboxDetail.artifacts.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {latestSandboxDetail.artifacts.map((a) => (
                    <SandboxArtifactCard key={a.id} artifact={a} />
                  ))}
                </div>
              ) : null}
              <pre className="mt-3 max-h-48 overflow-auto rounded-lg border border-white/[0.06] bg-black/40 p-3 font-mono text-xs text-white/60">
                {latestSandboxDetail.run.execution_log || "—"}
              </pre>
            </>
          ) : (
            <p className="mt-1 text-sm text-white/45">No sandbox run recorded for this patch yet.</p>
          )}
        </div>

        <div>
          <h3 className="text-sm font-semibold text-white/80">Grounding &amp; code signals</h3>
          <p className="mt-2 text-sm text-white/55">{rootCause.evidence.evidence_summary}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {rootCause.evidence.stack_trace_signals.map((s) => (
              <span
                key={s}
                className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[11px] text-white/60"
              >
                {s}
              </span>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-1 gap-1 text-sm sm:grid-cols-2">
            <RootCauseRow
              label="Suspected component"
              value={rootCause.evidence.suspected_component ?? "—"}
            />
            <RootCauseRow
              label="Evidence confidence"
              value={`${Math.round(rootCause.evidence.evidence_confidence * 100)}%`}
            />
            <RootCauseRow
              label="Commit SHA"
              value={rootCause.evidence.latest_commit_sha ?? "—"}
            />
          </div>
          {rootCause.evidence.code_candidates.length > 0 ? (
            <div className="mt-3 space-y-2">
              {rootCause.evidence.code_candidates.map((c) => (
                <div key={`${c.file_path}-${c.symbol}`} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2">
                  <p className="text-sm font-medium text-white/90">{c.file_path}</p>
                  <p className="text-xs text-white/45">{c.match_reason}</p>
                </div>
              ))}
            </div>
          ) : null}
          {rootCause.evidence.code_snippets.length > 0 ? (
            <div className="mt-3 space-y-2">
              {rootCause.evidence.code_snippets.map((s) => (
                <div
                  key={`${s.file_path}-${s.start_line}`}
                  className="overflow-hidden rounded-lg border border-white/[0.06] bg-black/30 p-2"
                >
                  <p className="text-xs text-white/70">
                    {s.file_path} (lines {s.start_line}–{s.end_line})
                  </p>
                  <pre className="mt-1 max-h-40 overflow-auto font-mono text-xs text-[#a5d4ff]">
                    {s.content}
                  </pre>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </details>
  );
}

function formatFailureCategory(category: FailureCategory): string {
  return category
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function ContextCard({ title, content }: { title: string; content: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-black/35 p-2">
      <p className="text-[9px] font-semibold uppercase text-white/40">{title}</p>
      <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[10px] leading-relaxed text-[#a5d4ff]">
        {content}
      </pre>
    </div>
  );
}

function serializeJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function MetaChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-2 py-1.5">
      <p className="text-[9px] font-semibold uppercase text-white/35">{label}</p>
      <p className="text-sm font-medium text-white/80">{value}</p>
    </div>
  );
}

function RootCauseRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-2 border-b border-white/[0.05] py-1.5 last:border-0">
      <span className="text-white/40">{label}</span>
      <span className="text-right text-sm text-white/85">{value}</span>
    </div>
  );
}

function SandboxStepCard({ step }: { step: SandboxRunStep }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-2 py-2 text-sm">
      <div className="flex justify-between gap-2">
        <span className="font-medium text-white/90">{step.step_name}</span>
        <span className="text-[10px] uppercase text-white/45">{step.status}</span>
      </div>
      <p className="text-xs text-white/50">{step.summary}</p>
    </div>
  );
}

function SandboxAttemptCard({ attempt }: { attempt: SandboxRunAttempt }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-2 py-2 text-sm text-white/70">
      Attempt {attempt.attempt_number}: {attempt.error_message ?? "—"} ({attempt.status})
    </div>
  );
}

function SandboxArtifactCard({ artifact }: { artifact: Artifact }) {
  return (
    <div className="rounded border border-white/[0.06] bg-white/[0.02] px-2 py-1.5 text-xs text-white/60">
      <span className="font-medium text-white/80">{artifact.artifact_type}</span> · {artifact.uri}
    </div>
  );
}
