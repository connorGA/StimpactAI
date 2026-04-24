"use client";

import { useMemo, useState } from "react";

import { DarkListboxSelect } from "@/components/dark-listbox-select";
import type { ProjectService, ProjectServiceRepairTarget } from "@/lib/types";

type ServiceRepairTargetPanelProps = {
  projectId: string;
  services: ProjectService[];
  initialTargets: ProjectServiceRepairTarget[];
};

function targetByServiceId(
  targets: ProjectServiceRepairTarget[],
): Map<string, ProjectServiceRepairTarget> {
  return new Map(targets.map((t) => [t.service_id, t]));
}

function uniqueBranchOptions(target: ProjectServiceRepairTarget | undefined): string[] {
  const names = new Set<string>();
  if (target?.default_branch) {
    names.add(target.default_branch);
  }
  if (target?.tracked_branch) {
    names.add(target.tracked_branch);
  }
  if (target?.selected_branch) {
    names.add(target.selected_branch);
  }
  for (const branch of target?.recent_branches ?? []) {
    if (branch.name) {
      names.add(branch.name);
    }
  }
  return [...names].sort((a, b) => a.localeCompare(b));
}

function buildServiceUpdateBody(
  service: ProjectService,
  trackedBranch: string | null,
): Record<string, unknown> {
  return {
    name: service.name,
    slug: service.slug,
    service_type: service.service_type,
    repo_profile_id: service.repo_profile_id,
    owner: service.owner,
    deploy_target: service.deploy_target,
    tracked_branch: trackedBranch,
    routing_hints: service.routing_hints,
    startup_priority: service.startup_priority,
    sandbox_healthcheck_command: service.sandbox_healthcheck_command,
    sandbox_healthcheck_url: service.sandbox_healthcheck_url,
    active: service.active,
    dependencies: service.dependencies.map((d) => ({
      depends_on_service_id: d.depends_on_service_id,
      dependency_kind: d.dependency_kind,
    })),
  };
}

function formatSourceLabel(source: ProjectServiceRepairTarget["selected_source"]): string {
  switch (source) {
    case "deployed_commit":
      return "Live telemetry (deployed commit)";
    case "tracked_branch":
      return "Tracked branch";
    case "default_branch":
      return "Repository default branch";
    default:
      return source;
  }
}

function isCustomBranchDraft(
  draft: string,
  options: string[],
): boolean {
  return draft !== "" && !options.includes(draft);
}

export function ServiceRepairTargetPanel({
  projectId,
  services,
  initialTargets,
}: ServiceRepairTargetPanelProps) {
  const [targets, setTargets] = useState(() => targetByServiceId(initialTargets));
  const [draftBranches, setDraftBranches] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const service of services) {
      const t = initialTargets.find((x) => x.service_id === service.id);
      initial[service.id] = t?.tracked_branch ?? t?.selected_branch ?? "";
    }
    return initial;
  });
  const [customBranchById, setCustomBranchById] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    for (const service of services) {
      const t = initialTargets.find((x) => x.service_id === service.id);
      const opts = uniqueBranchOptions(t);
      const draft = t?.tracked_branch ?? t?.selected_branch ?? "";
      initial[service.id] = isCustomBranchDraft(draft, opts);
    }
    return initial;
  });
  const [savingId, setSavingId] = useState<string | null>(null);
  const [errorById, setErrorById] = useState<Record<string, string | null>>({});

  const orderedServices = useMemo(
    () => [...services].sort((a, b) => a.name.localeCompare(b.name)),
    [services],
  );

  async function refreshTarget(serviceId: string) {
    const response = await fetch(
      `/api/onboarding/projects/${encodeURIComponent(projectId)}/services/${encodeURIComponent(serviceId)}/repair-target?branch_limit=20`,
      { method: "GET", cache: "no-store" },
    );
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(text || `Refresh failed (${response.status})`);
    }
    const payload = (await response.json()) as ProjectServiceRepairTarget;
    setTargets((prev) => {
      const next = new Map(prev);
      next.set(serviceId, payload);
      return next;
    });
    const nextDraft = payload.tracked_branch ?? payload.selected_branch ?? "";
    const opts = uniqueBranchOptions(payload);
    setDraftBranches((prev) => ({
      ...prev,
      [serviceId]: nextDraft,
    }));
    setCustomBranchById((prev) => ({
      ...prev,
      [serviceId]: isCustomBranchDraft(nextDraft, opts),
    }));
  }

  async function handleSave(service: ProjectService) {
    const raw = draftBranches[service.id] ?? "";
    const trackedBranch = raw.trim() === "" ? null : raw.trim();

    setSavingId(service.id);
    setErrorById((prev) => ({ ...prev, [service.id]: null }));
    try {
      const response = await fetch(
        `/api/onboarding/projects/${encodeURIComponent(projectId)}/services/${encodeURIComponent(service.id)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildServiceUpdateBody(service, trackedBranch)),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: { message?: string } } | null;
        throw new Error(payload?.error?.message ?? `Save failed (${response.status})`);
      }
      await refreshTarget(service.id);
    } catch (error) {
      setErrorById((prev) => ({
        ...prev,
        [service.id]: error instanceof Error ? error.message : "Save failed.",
      }));
    } finally {
      setSavingId(null);
    }
  }

  if (orderedServices.length === 0) {
    return (
      <p className="text-sm text-white/50">
        Map at least one project service to a repo profile to configure repair targets.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {orderedServices.map((service) => {
        const target = targets.get(service.id);
        const options = uniqueBranchOptions(target);
        const draft = draftBranches[service.id] ?? "";
        const customMode = customBranchById[service.id] ?? false;
        const selectValue = customMode
          ? "__custom__"
          : draft === ""
            ? ""
            : options.includes(draft)
              ? draft
              : "__custom__";
        const error = errorById[service.id];

        const branchMenuOptions =
          options.length > 0
            ? [
                { value: "", label: "Use repository default" },
                ...options.map((name) => ({ value: name, label: name })),
                { value: "__custom__", label: "Custom branch…" },
              ]
            : [];

        return (
          <div
            key={service.id}
            className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium text-white">{service.name}</p>
                <p className="mt-1 text-xs text-white/45">
                  Slug <code className="text-[#93c5fd]">{service.slug}</code>
                  {service.repo_profile_id ? null : (
                    <span className="ml-2 text-[#ffb253]">· No repo profile</span>
                  )}
                </p>
              </div>
              {target ? (
                <div className="text-right text-xs leading-5 text-white/50">
                  <p>
                    <span className="font-semibold text-white/65">Source:</span>{" "}
                    {formatSourceLabel(target.selected_source)}
                  </p>
                  {target.deployed_commit_sha ? (
                    <p className="mt-0.5">
                      Deployed SHA:{" "}
                      <code className="text-[11px] text-[#93c5fd]">
                        {target.deployed_commit_sha.slice(0, 12)}
                      </code>
                      {target.deployed_environment ? ` (${target.deployed_environment})` : null}
                    </p>
                  ) : (
                    <p className="mt-0.5">No deployed commit from telemetry yet.</p>
                  )}
                  {target.current_target_commit_sha ? (
                    <p className="mt-0.5">
                      Target SHA:{" "}
                      <code className="text-[11px] text-[#93c5fd]">
                        {target.current_target_commit_sha.slice(0, 12)}
                      </code>
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-sm">
                <span className="font-medium text-white/75">Tracked branch</span>
                <span className="text-xs text-white/40">
                  When telemetry has no commit SHA. Empty = repository default.
                </span>
                {branchMenuOptions.length > 0 ? (
                  <DarkListboxSelect
                    className="mt-1"
                    aria-label={`Tracked branch for ${service.name}`}
                    value={selectValue}
                    onChange={(value) => {
                      if (value === "__custom__") {
                        setCustomBranchById((prev) => ({ ...prev, [service.id]: true }));
                        return;
                      }
                      setCustomBranchById((prev) => ({ ...prev, [service.id]: false }));
                      setDraftBranches((prev) => ({ ...prev, [service.id]: value }));
                    }}
                    size="comfortable"
                    options={branchMenuOptions}
                  />
                ) : null}
                {options.length === 0 || customMode ? (
                  <input
                    type="text"
                    className="mt-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-white/35 focus:border-[#ff6a3d]/40"
                    placeholder="e.g. main, develop"
                    value={draft}
                    onChange={(event) => {
                      const next = event.target.value;
                      setDraftBranches((prev) => ({ ...prev, [service.id]: next }));
                      if (options.length > 0) {
                        setCustomBranchById((prev) => ({
                          ...prev,
                          [service.id]: isCustomBranchDraft(next, options),
                        }));
                      }
                    }}
                  />
                ) : null}
              </label>
              <button
                type="button"
                className="shrink-0 rounded-lg bg-[#ff6a3d] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#e85a30] disabled:cursor-not-allowed disabled:opacity-50"
                disabled={savingId === service.id || !service.repo_profile_id}
                onClick={() => void handleSave(service)}
              >
                {savingId === service.id ? "Saving…" : "Save branch"}
              </button>
            </div>
            {error ? (
              <p className="mt-2 text-sm text-[#fca5a5]" role="alert">
                {error}
              </p>
            ) : null}
            {!service.repo_profile_id ? (
              <p className="mt-2 text-xs text-white/40">
                Map a repo profile in onboarding before saving a branch.
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
