"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { DarkListboxSelect } from "@/components/dark-listbox-select";
import type { AutonomyMode, ProjectPolicy } from "@/lib/types";

type ControlCenterPolicyFormProps = {
  projectId: string;
  initialPolicy: ProjectPolicy;
};

const AUTONOMY_OPTIONS: { value: AutonomyMode; label: string; hint: string }[] = [
  {
    value: "observe",
    label: "Observe",
    hint: "Incidents only — no autonomous execution.",
  },
  {
    value: "recommend",
    label: "Recommend",
    hint: "Guidance and plans; no write-back without approval.",
  },
  {
    value: "supervised_execute",
    label: "Supervised execute",
    hint: "Execution after operator approval.",
  },
  {
    value: "autonomous",
    label: "Autonomous",
    hint: "Trusted flows within guardrails below.",
  },
];

function policyToFormState(policy: ProjectPolicy) {
  return {
    autonomy_mode: policy.autonomy_mode,
    require_human_approval: policy.require_human_approval,
    allow_production_writes: policy.allow_production_writes,
    allow_low_risk_autonomy: policy.allow_low_risk_autonomy,
    block_during_active_deploys: policy.block_during_active_deploys,
    restrict_to_approved_services: policy.restrict_to_approved_services,
    require_rollback_plan: policy.require_rollback_plan,
    require_post_action_verification: policy.require_post_action_verification,
    approved_services_text: policy.approved_services.join(", "),
    failure_classifier_enabled: policy.failure_classifier_enabled,
    root_cause_enabled: policy.root_cause_enabled,
    patch_planner_enabled: policy.patch_planner_enabled,
    runbook_executor_enabled: policy.runbook_executor_enabled,
  };
}

type FormState = ReturnType<typeof policyToFormState>;

export function ControlCenterPolicyForm({ projectId, initialPolicy }: ControlCenterPolicyFormProps) {
  const router = useRouter();
  const [state, setState] = useState<FormState>(() => policyToFormState(initialPolicy));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    setState(policyToFormState(initialPolicy));
    setSavedAt(null);
  }, [initialPolicy]);

  const dirty = useMemo(
    () => JSON.stringify(state) !== JSON.stringify(policyToFormState(initialPolicy)),
    [state, initialPolicy],
  );

  const update = useCallback(<K extends keyof FormState>(key: K, value: FormState[K]) => {
    setState((s) => ({ ...s, [key]: value }));
    setError(null);
    setSavedAt(null);
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSavedAt(null);

    const approved_services = state.approved_services_text
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 50);

    const body = {
      autonomy_mode: state.autonomy_mode,
      require_human_approval: state.require_human_approval,
      allow_production_writes: state.allow_production_writes,
      allow_low_risk_autonomy: state.allow_low_risk_autonomy,
      block_during_active_deploys: state.block_during_active_deploys,
      restrict_to_approved_services: state.restrict_to_approved_services,
      require_rollback_plan: state.require_rollback_plan,
      require_post_action_verification: state.require_post_action_verification,
      approved_services,
      failure_classifier_enabled: state.failure_classifier_enabled,
      root_cause_enabled: state.root_cause_enabled,
      patch_planner_enabled: state.patch_planner_enabled,
      runbook_executor_enabled: state.runbook_executor_enabled,
    };

    try {
      const response = await fetch(
        `/api/onboarding/projects/${encodeURIComponent(projectId)}/policy`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      const payload = (await response.json().catch(() => null)) as
        | ProjectPolicy
        | { error?: { message?: string } }
        | null;
      if (!response.ok) {
        const msg =
          payload && "error" in payload && payload.error?.message
            ? payload.error.message
            : `Save failed (${response.status})`;
        throw new Error(msg);
      }
      if (!payload || !("autonomy_mode" in payload)) {
        throw new Error("Invalid response from server.");
      }
      const next = policyToFormState(payload as ProjectPolicy);
      setState(next);
      setSavedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={(e) => void handleSubmit(e)}
      className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
            Project policy
          </h2>
          <p className="mt-1 text-sm text-white/50">
            Autonomy mode, safety guardrails, and agent capabilities for this project.
          </p>
        </div>
        <button
          type="submit"
          disabled={saving || !dirty}
          className="rounded-lg bg-[#ff6a3d] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#e85a30] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>

      {error ? (
        <p className="mt-3 text-sm text-[#fca5a5]" role="alert">
          {error}
        </p>
      ) : null}
      {savedAt && !error ? (
        <p className="mt-3 text-sm text-[#86efac]">Saved at {savedAt}</p>
      ) : null}

      <div className="mt-5 space-y-5">
        <div>
          <label className="text-xs font-medium text-white/65">Autonomy mode</label>
          <DarkListboxSelect
            className="mt-1.5 max-w-md"
            aria-label="Autonomy mode"
            value={state.autonomy_mode}
            onChange={(v) => update("autonomy_mode", v as AutonomyMode)}
            options={AUTONOMY_OPTIONS.map((opt) => ({
              value: opt.value,
              label: opt.label,
            }))}
            size="comfortable"
          />
          <p className="mt-1.5 text-xs text-white/40">
            {AUTONOMY_OPTIONS.find((o) => o.value === state.autonomy_mode)?.hint}
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <ToggleRow
            label="Require human approval"
            description="Gate promotions or sensitive steps on explicit approval."
            checked={state.require_human_approval}
            onChange={(v) => update("require_human_approval", v)}
          />
          <ToggleRow
            label="Allow production writes"
            description="Permit change proposals or actions targeting production."
            checked={state.allow_production_writes}
            onChange={(v) => update("allow_production_writes", v)}
          />
          <ToggleRow
            label="Allow low-risk autonomy"
            description="Let the platform take narrower automated actions when risk is low."
            checked={state.allow_low_risk_autonomy}
            onChange={(v) => update("allow_low_risk_autonomy", v)}
          />
          <ToggleRow
            label="Block during active deploys"
            description="Pause autonomous work while deploy signals are active."
            checked={state.block_during_active_deploys}
            onChange={(v) => update("block_during_active_deploys", v)}
          />
          <ToggleRow
            label="Restrict to approved services"
            description="Only run automation for services in the allowlist below."
            checked={state.restrict_to_approved_services}
            onChange={(v) => update("restrict_to_approved_services", v)}
          />
          <ToggleRow
            label="Require rollback plan"
            description="Expect a rollback path before applying risky changes."
            checked={state.require_rollback_plan}
            onChange={(v) => update("require_rollback_plan", v)}
          />
          <ToggleRow
            label="Require post-action verification"
            description="Enforce verification after remediation steps."
            checked={state.require_post_action_verification}
            onChange={(v) => update("require_post_action_verification", v)}
          />
        </div>

        <div>
          <label className="text-xs font-medium text-white/65">Approved services</label>
          <p className="mt-0.5 text-xs text-white/40">
            Comma-separated names or slugs (used when restrict is on). Max 50 entries.
          </p>
          <textarea
            className="mt-1.5 min-h-[72px] w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#ff6a3d]/40"
            placeholder="api, web, worker"
            value={state.approved_services_text}
            onChange={(ev) => update("approved_services_text", ev.target.value)}
          />
        </div>

        <div>
          <p className="text-xs font-medium text-white/65">Agent capabilities</p>
          <p className="mt-0.5 text-xs text-white/40">
            Turn platform analysis and execution features on or off for this project.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <ToggleRow
              label="Failure classifier"
              description="Categorize incidents before deeper analysis."
              checked={state.failure_classifier_enabled}
              onChange={(v) => update("failure_classifier_enabled", v)}
            />
            <ToggleRow
              label="Root cause analysis"
              description="Grounded RCA from traces and code context."
              checked={state.root_cause_enabled}
              onChange={(v) => update("root_cause_enabled", v)}
            />
            <ToggleRow
              label="Patch planner"
              description="Draft fixes and patch summaries."
              checked={state.patch_planner_enabled}
              onChange={(v) => update("patch_planner_enabled", v)}
            />
            <ToggleRow
              label="Runbook executor"
              description="Allow playbook-driven remediation."
              checked={state.runbook_executor_enabled}
              onChange={(v) => update("runbook_executor_enabled", v)}
            />
          </div>
        </div>
      </div>
    </form>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-white/8 bg-black/20 px-3 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-white/90">{label}</p>
        <p className="mt-0.5 text-xs text-white/45">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-7 w-12 shrink-0 rounded-full transition ${
          checked ? "bg-[#ff6a3d]" : "bg-white/15"
        }`}
      >
        <span
          className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition ${
            checked ? "left-5" : "left-0.5"
          }`}
        />
      </button>
    </div>
  );
}
