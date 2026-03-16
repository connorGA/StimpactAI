import { PageHeader, PreviewNotice } from "@/components/dashboard-ui";

const autonomyModes = [
  {
    name: "Observe",
    detail: "The platform analyzes incidents but never recommends or acts.",
    active: false,
  },
  {
    name: "Recommend",
    detail: "Draft guidance is allowed, but execution remains fully manual.",
    active: true,
  },
  {
    name: "Supervised execute",
    detail: "Low-risk playbooks may run after explicit operator approval.",
    active: false,
  },
  {
    name: "Autonomous",
    detail: "Trusted remediations may execute inside strict guardrails.",
    active: false,
  },
];

const agentConfigs = [
  "Failure classifier",
  "Root cause analyzer",
  "Patch planner",
  "Runbook executor",
];

const guardrailRows = [
  "Require approval for production writes",
  "Block actions during active deploys",
  "Restrict autonomous actions to approved services",
  "Require rollback plan generation",
  "Post-action verification is mandatory",
];

export default function ControlCenterPage() {
  return (
    <main className="space-y-8">
      <PageHeader
        eyebrow="Control center"
        title="Autonomy policy, guardrails, and agent permissions"
        description="The control center now reads more like an enterprise settings console than a dashboard: explicit sections, durable policy language, and less decorative surface noise."
      />

      <section className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <section className="ops-sheet-dark rounded-[28px] p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/48">
            Current posture
          </p>
          <h2 className="mt-3 text-3xl font-semibold">Recommend mode</h2>
          <p className="mt-3 text-sm leading-6 text-white/72">
            Human operators remain in control while the platform drafts analysis
            and suggested actions.
          </p>

          <div className="ops-row-divider mt-6">
            <PolicyChip label="Approval path" value="Human-in-loop" />
            <PolicyChip label="Production writes" value="Blocked" />
            <PolicyChip label="Blast radius" value="Low-risk only" />
          </div>
        </section>

        <section className="ops-sheet rounded-[28px] p-6">
          <p className="ops-kicker text-[11px] font-semibold uppercase">
            Autonomy modes
          </p>
          <div className="mt-5 border-t border-[rgba(24,24,27,0.08)]">
            {autonomyModes.map((mode) => (
              <div
                key={mode.name}
                className={`flex flex-col gap-4 border-b border-[rgba(24,24,27,0.08)] py-5 last:border-b-0 xl:flex-row xl:items-center xl:justify-between ${
                  mode.active
                    ? "bg-[rgba(255,255,255,0.22)]"
                    : ""
                }`}
              >
                <div className="max-w-xl">
                  <div className="flex items-center gap-3">
                    <h3 className="text-base font-semibold text-[#111827]">{mode.name}</h3>
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${
                        mode.active ? "vault-dot" : "bg-[#cbd5e1]"
                      }`}
                    />
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[#667085]">{mode.detail}</p>
                </div>
                <button
                  type="button"
                  className={`rounded-full px-4 py-2 text-sm font-semibold ${
                    mode.active
                      ? "ops-button text-white"
                      : "ops-button-secondary"
                  }`}
                >
                  {mode.active ? "Current mode" : "Select"}
                </button>
              </div>
            ))}
          </div>
        </section>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <section className="ops-sheet rounded-[28px] p-6">
          <p className="ops-kicker text-[11px] font-semibold uppercase">
            Guardrails
          </p>
          <div className="mt-5 border-t border-[rgba(24,24,27,0.08)]">
            {guardrailRows.map((row, index) => (
              <div
                key={row}
                className="flex items-center justify-between gap-4 border-b border-[rgba(24,24,27,0.08)] py-4 last:border-b-0"
              >
                <div>
                  <p className="font-medium text-[#111827]">{row}</p>
                  <p className="mt-1 text-sm text-[#667085]">
                    Visible now as configuration UI. Backend enforcement wiring
                    is still pending.
                  </p>
                </div>
                <ToggleSwitch checked={index < 4} />
              </div>
            ))}
          </div>
        </section>

        <section className="ops-sheet-muted rounded-[28px] p-6">
          <p className="ops-kicker text-[11px] font-semibold uppercase">
            Agent configuration
          </p>
          <div className="mt-5 border-t border-[rgba(24,24,27,0.08)]">
            {agentConfigs.map((agent, index) => (
              <div
                key={agent}
                className="border-b border-[rgba(24,24,27,0.08)] py-4 last:border-b-0"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-medium text-[#111827]">{agent}</p>
                    <p className="mt-1 text-sm leading-6 text-[#667085]">
                      Per-agent configuration panels, thresholds, and approval
                      bindings will live here.
                    </p>
                  </div>
                  <ToggleSwitch checked={index !== 3} />
                </div>
              </div>
            ))}
          </div>
        </section>
      </section>

      <PreviewNotice
        title="Control-center features still not configured"
        items={[
          "Mode switching, policy storage, and environment-specific enforcement are not wired yet.",
          "Blast-radius scoring and simulation are shown as product direction only.",
          "Real guardrail enforcement will attach once automation execution exists in later phases.",
        ]}
      />
    </main>
  );
}

function PolicyChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="py-4 first:pt-0 last:pb-0">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/48">
        {label}
      </p>
      <p className="mt-2 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function ToggleSwitch({ checked }: { checked: boolean }) {
  return (
    <button
      type="button"
      className={`relative h-7 w-12 rounded-full transition ${
        checked ? "bg-[var(--vault-orange)]" : "bg-[#cbd5e1]"
      }`}
      aria-pressed={checked}
    >
      <span
        className={`absolute top-1 h-5 w-5 rounded-full bg-white transition ${
          checked ? "left-6" : "left-1"
        }`}
      />
    </button>
  );
}
