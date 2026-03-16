import Link from "next/link";
import { notFound } from "next/navigation";

import { ChatPanel } from "@/components/chat-panel";
import { PageHeader, PreviewNotice, SectionCard } from "@/components/dashboard-ui";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { AgentPlatformError, getIncident } from "@/lib/agent-platform";
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

  try {
    detail = await getIncident(incidentId, { eventLimit: 100 });
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
        </section>

        <div className="space-y-6">
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

          <PreviewNotice
            title="Detail-page features still to be connected"
            items={[
              "Deploy correlation, assignee ownership, and linked change requests are not wired yet.",
              "Root-cause suggestions and patch recommendations will appear here in later phases.",
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
