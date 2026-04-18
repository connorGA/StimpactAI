import Link from "next/link";

import {
  AgentPlatformError,
  getSuppressionSummary,
  listSuppressedTelemetry,
} from "@/lib/agent-platform";
import { resolvePrimaryProjectId } from "@/lib/project-context";
import type { SuppressedFingerprint, SuppressionSummary } from "@/lib/types";
import { NoiseReclassifyForm } from "@/components/noise-reclassify-form";

export const dynamic = "force-dynamic";

type NoisePageProps = {
  searchParams: Promise<{ project_id?: string }>;
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value ?? "—";
  }
}

function classificationBadge(classification: string): string {
  switch (classification) {
    case "user_error":
      return "border-[rgba(125,211,252,0.3)] bg-[rgba(125,211,252,0.12)] text-[#7dd3fc]";
    case "code_ambiguous":
      return "border-[rgba(255,178,83,0.3)] bg-[rgba(255,178,83,0.12)] text-[#ffb253]";
    case "code_bug":
      return "border-[rgba(255,106,61,0.3)] bg-[rgba(255,106,61,0.12)] text-[#ffb99a]";
    default:
      return "border-white/10 bg-white/[0.04] text-white/70";
  }
}

export default async function NoisePage({ searchParams }: NoisePageProps) {
  const params = await searchParams;
  const projectId =
    params.project_id?.trim() || (await resolvePrimaryProjectId()) || undefined;

  if (!projectId) {
    return (
      <main className="mx-auto max-w-[1120px] px-4 py-12 text-sm text-white/70">
        <p>Create a project to view suppressed telemetry.</p>
      </main>
    );
  }

  let listLoadError: string | null = null;
  let listResponse: { items: SuppressedFingerprint[] };
  try {
    listResponse = await listSuppressedTelemetry(projectId, { limit: 100 });
  } catch (caught) {
    const message =
      caught instanceof AgentPlatformError
        ? caught.message
        : "Unable to load suppressed telemetry.";
    listLoadError = message;
    listResponse = { items: [] };
  }

  const summary = await getSuppressionSummary(projectId, {
    windowMinutes: 60 * 24,
  }).catch<SuppressionSummary | null>(() => null);

  const items = listResponse.items;

  return (
    <main className="mx-auto max-w-[1120px] space-y-6 px-4 pb-12 pt-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-white/50">
            Suppressed telemetry
          </div>
          <h1 className="mt-1 text-2xl font-bold text-white">Noise review</h1>
          <p className="mt-1 max-w-2xl text-sm text-white/60">
            Telemetry the classifier filtered out of the incident triage pipeline. Flip a
            fingerprint to <span className="text-white">code_bug</span> if you see
            something that should trigger an autonomous repair run.
          </p>
        </div>
        <Link
          href={`/incidents?project_id=${encodeURIComponent(projectId)}`}
          className="rounded-lg border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-xs font-medium text-white/80 transition hover:bg-white/[0.08]"
        >
          Back to incidents
        </Link>
      </div>

      {summary ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Card
            label="User-error events (24h)"
            value={String(summary.user_error_event_count)}
            hint={`${summary.user_error_unique_fingerprints} unique fingerprints`}
          />
          <Card
            label="Ambiguous events (24h)"
            value={String(summary.code_ambiguous_event_count)}
            hint={`${summary.code_ambiguous_unique_fingerprints} unique fingerprints`}
          />
          <Card
            label="Window"
            value={`${Math.round(summary.window_minutes / 60)}h`}
            hint="Summary window"
          />
          <Card
            label="Fingerprints shown"
            value={String(items.length)}
            hint="Most recent suppressed fingerprints"
          />
        </div>
      ) : null}

      {listLoadError ? (
        <p className="rounded-xl border border-[#ff6a3d]/35 bg-[#ff6a3d]/[0.06] px-4 py-4 text-sm text-[#ffb099]">
          {listLoadError}
        </p>
      ) : null}

      {!listLoadError && items.length === 0 ? (
        <p className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-6 text-sm text-white/60">
          No suppressed telemetry in the window. This list fills in as the classifier
          filters out expected user errors.
        </p>
      ) : null}

      {!listLoadError && items.length > 0 ? (
        <div className="overflow-visible rounded-xl border border-white/10">
          <table className="min-w-full divide-y divide-white/5 text-sm">
            <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wide text-white/50">
              <tr>
                <th className="px-4 py-2 text-left font-semibold">Fingerprint</th>
                <th className="px-4 py-2 text-left font-semibold">Service</th>
                <th className="px-4 py-2 text-left font-semibold">Classification</th>
                <th className="px-4 py-2 text-left font-semibold">Count</th>
                <th className="px-4 py-2 text-left font-semibold">Last seen</th>
                <th className="px-4 py-2 text-left font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-white/80">
              {items.map((item) => (
                <tr key={`${item.project_id}:${item.fingerprint}`} className="align-top">
                  <td className="max-w-[320px] px-4 py-3">
                    <div className="font-mono text-[11px] text-white/50">
                      {item.fingerprint.slice(0, 12)}…
                    </div>
                    <div className="mt-1 line-clamp-2 text-[13px] text-white/80">
                      {item.error_message}
                    </div>
                    {item.classification_reason ? (
                      <div className="mt-1 text-[11px] text-white/50">
                        {item.classification_reason}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-[13px] text-white/70">{item.service}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${classificationBadge(
                        item.classification,
                      )}`}
                    >
                      {item.classification}
                    </span>
                    {item.classification_source ? (
                      <div className="mt-1 text-[10px] uppercase tracking-wide text-white/40">
                        via {item.classification_source}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-[13px] text-white/70">
                    {item.occurrence_count}
                  </td>
                  <td className="px-4 py-3 text-[12px] text-white/60">
                    {formatDate(item.last_occurred_at)}
                  </td>
                  <td className="px-4 py-3">
                    <NoiseReclassifyForm
                      projectId={item.project_id}
                      fingerprint={item.fingerprint}
                      currentClassification={item.classification}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </main>
  );
}

function Card({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-white/50">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
      {hint ? <div className="mt-0.5 text-[11px] text-white/50">{hint}</div> : null}
    </div>
  );
}
