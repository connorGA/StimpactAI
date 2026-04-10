"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getTelemetryVerificationCopy,
  getTelemetryVerificationStatusLabel,
} from "@/components/onboarding-step-six-state";
import type {
  ProjectService,
  ProjectTelemetryHeartbeat,
  ProjectTelemetryVerification,
} from "@/lib/types";

type LiveManualPingPanelProps = {
  projectId: string;
  services: ProjectService[];
  heartbeats: ProjectTelemetryHeartbeat[];
};

type ManualPingWindow = Window & {
  pingStimpact?: () => Promise<void>;
  __stimpact?: {
    ping?: () => Promise<void>;
  };
};

const BROWSER_SERVICE_TYPES = new Set<ProjectService["service_type"]>(["frontend", "fullstack"]);

export function LiveManualPingPanel({
  projectId,
  services,
  heartbeats,
}: LiveManualPingPanelProps) {
  const serviceOptions = useMemo(() => buildServiceOptions(services, heartbeats), [heartbeats, services]);
  const defaultTarget = useMemo(() => buildDefaultTarget(serviceOptions, heartbeats), [heartbeats, serviceOptions]);
  const [selectedService, setSelectedService] = useState(defaultTarget.service);
  const [environment, setEnvironment] = useState(defaultTarget.environment);
  const [verification, setVerification] = useState<ProjectTelemetryVerification | null>(null);
  const [loadingVerification, setLoadingVerification] = useState(false);
  const [triggeringPing, setTriggeringPing] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    setSelectedService((current) => current || defaultTarget.service);
    setEnvironment((current) => current || defaultTarget.environment);
  }, [defaultTarget.environment, defaultTarget.service]);

  const loadVerification = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}): Promise<ProjectTelemetryVerification | null> => {
      if (!projectId.trim() || !selectedService.trim()) {
        setVerification(null);
        return null;
      }
      if (!silent) {
        setLoadingVerification(true);
      }
      try {
        const params = new URLSearchParams({
          service: selectedService.trim(),
          environment: environment.trim() || "production",
        });
        const response = await fetch(
          `/api/onboarding/projects/${encodeURIComponent(projectId.trim())}/telemetry-verification?${params.toString()}`,
          {
            method: "GET",
            headers: {
              "Content-Type": "application/json",
            },
          },
        );
        if (!response.ok) {
          let message = `Heartbeat check failed with status ${response.status}.`;
          try {
            const payload = (await response.json()) as {
              error?: { message?: string };
            };
            if (payload.error?.message) {
              message = payload.error.message;
            }
          } catch {
            // Keep the default fallback message when the response is not JSON.
          }
          throw new Error(message);
        }
        const payload = (await response.json()) as ProjectTelemetryVerification;
        setVerification(payload);
        setErrorMessage(null);
        return payload;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Unable to load live heartbeat verification.";
        setErrorMessage(message);
        return null;
      } finally {
        if (!silent) {
          setLoadingVerification(false);
        }
      }
    },
    [environment, projectId, selectedService],
  );

  useEffect(() => {
    void loadVerification();
  }, [loadVerification]);

  const handleManualPing = useCallback(async () => {
    const ping = resolveManualPing();
    if (!ping) {
      setErrorMessage(
        "Manual ping is unavailable in this browser session. Open the SDK-enabled app surface that loaded the generated helper, then try again here.",
      );
      setStatusMessage(null);
      return;
    }
    setTriggeringPing(true);
    setErrorMessage(null);
    setStatusMessage("Manual ping sent. Waiting for the fresh heartbeat to land...");
    const previousLastSeenAt = verification?.last_seen_at ?? null;
    try {
      await ping();
      setLoadingVerification(true);
      const refreshed = await pollForVerification({
        projectId,
        service: selectedService.trim(),
        environment: environment.trim() || "production",
        previousLastSeenAt,
      });
      if (refreshed) {
        setVerification(refreshed);
        setStatusMessage(
          refreshed.last_seen_at && refreshed.last_seen_at !== previousLastSeenAt
            ? "Manual ping received. Live heartbeat verification is now refreshed."
            : "Manual ping completed. Verification was refreshed, but the timestamp has not advanced yet.",
        );
      } else {
        setStatusMessage(
          "Manual ping was sent. If the SDK is active in this runtime, the heartbeat status should refresh shortly.",
        );
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Manual ping failed.");
    } finally {
      setLoadingVerification(false);
      setTriggeringPing(false);
    }
  }, [environment, projectId, selectedService, verification?.last_seen_at]);

  const statusLabel = getTelemetryVerificationStatusLabel(verification, null, loadingVerification);
  const statusCopy = getTelemetryVerificationCopy(verification, null);
  const hasTargets = serviceOptions.length > 0;

  return (
    <section className="ops-sheet rounded-[28px] p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="ops-kicker text-[11px] font-semibold uppercase">Manual live check</p>
          <h2 className="mt-2 text-2xl font-semibold text-[#171717]">Trigger a one-off SDK ping</h2>
        </div>
        <span
          className={`inline-flex rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
            verification?.status === "healthy"
              ? "bg-[linear-gradient(180deg,#22c55e,#16a34a)] text-white"
              : verification?.status === "stale"
                ? "bg-[rgba(245,158,11,0.14)] text-[#9a5b14]"
                : "bg-[rgba(24,24,27,0.08)] text-[#5f6470]"
          }`}
        >
          {statusLabel}
        </span>
      </div>

      <p className="mt-4 text-sm leading-6 text-[#746d66]">
        Use this when the monitored browser app is open in the current session and you want to force an
        immediate heartbeat instead of waiting for the scheduled interval.
      </p>

      <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
        <label className="flex flex-col gap-2 text-sm font-medium text-[#171717]">
          Service
          <select
            value={selectedService}
            onChange={(event) => {
              setSelectedService(event.target.value);
              setStatusMessage(null);
              setErrorMessage(null);
            }}
            disabled={!hasTargets}
            className="rounded-[16px] border border-[rgba(24,24,27,0.12)] bg-white px-4 py-3 text-sm text-[#171717] outline-none transition focus:border-[rgba(45,127,249,0.45)] focus:ring-2 focus:ring-[rgba(45,127,249,0.12)]"
          >
            {hasTargets ? (
              serviceOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))
            ) : (
              <option value="">No service targets found</option>
            )}
          </select>
        </label>

        <label className="flex flex-col gap-2 text-sm font-medium text-[#171717]">
          Environment
          <input
            value={environment}
            onChange={(event) => {
              setEnvironment(event.target.value);
              setStatusMessage(null);
              setErrorMessage(null);
            }}
            placeholder="production"
            className="rounded-[16px] border border-[rgba(24,24,27,0.12)] bg-white px-4 py-3 text-sm text-[#171717] outline-none transition focus:border-[rgba(45,127,249,0.45)] focus:ring-2 focus:ring-[rgba(45,127,249,0.12)]"
          />
        </label>
      </div>

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => {
            void handleManualPing();
          }}
          disabled={!hasTargets || !selectedService.trim() || triggeringPing}
          className="ops-button inline-flex rounded-full px-4 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
        >
          {triggeringPing ? "Sending ping" : "Send manual ping"}
        </button>
        <button
          type="button"
          onClick={() => {
            void loadVerification();
          }}
          disabled={!hasTargets || !selectedService.trim() || loadingVerification}
          className="ops-button-secondary inline-flex rounded-full px-4 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loadingVerification ? "Refreshing" : "Refresh heartbeat"}
        </button>
      </div>

      <div className="mt-5 rounded-[20px] border border-[rgba(24,24,27,0.08)] bg-white/55 px-4 py-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8f735c]">
          Last heartbeat
        </p>
        <p className="mt-2 text-sm font-semibold text-[#171717]">
          {verification?.last_seen_at ? formatHeartbeatTimestamp(verification.last_seen_at) : "Not seen yet"}
        </p>
        <p className="mt-3 text-sm leading-6 text-[#5f6470]">{statusCopy}</p>
      </div>

      {statusMessage ? (
        <p className="mt-4 rounded-[18px] bg-[rgba(45,127,249,0.10)] px-4 py-3 text-sm leading-6 text-[#173fbe]">
          {statusMessage}
        </p>
      ) : null}
      {errorMessage ? (
        <p className="mt-4 rounded-[18px] bg-[rgba(233,89,80,0.10)] px-4 py-3 text-sm leading-6 text-[#b4453d]">
          {errorMessage}
        </p>
      ) : null}

      <p className="mt-4 text-xs leading-6 text-[#8a8178]">
        This button can only trigger a ping from the app runtime that actually loaded the generated
        browser helper. If the monitored app is hosted separately, open that app in this browser first so
        the helper can register itself before using this control.
      </p>
    </section>
  );
}

function resolveManualPing(): (() => Promise<void>) | null {
  if (typeof window === "undefined") {
    return null;
  }
  const scope = window as ManualPingWindow;
  if (typeof scope.pingStimpact === "function") {
    return scope.pingStimpact;
  }
  if (typeof scope.__stimpact?.ping === "function") {
    return scope.__stimpact.ping;
  }
  return null;
}

function buildServiceOptions(
  services: ProjectService[],
  heartbeats: ProjectTelemetryHeartbeat[],
): string[] {
  const heartbeatNames = dedupeValues(heartbeats.map((item) => item.service));
  const browserServiceNames = dedupeValues(
    services
      .filter((service) => BROWSER_SERVICE_TYPES.has(service.service_type))
      .map((service) => service.name),
  );
  const fallbackServiceNames = dedupeValues(services.map((service) => service.name));
  if (heartbeatNames.length > 0) {
    return heartbeatNames;
  }
  if (browserServiceNames.length > 0) {
    return browserServiceNames;
  }
  return fallbackServiceNames;
}

function buildDefaultTarget(
  serviceOptions: string[],
  heartbeats: ProjectTelemetryHeartbeat[],
): { service: string; environment: string } {
  const latestHeartbeat = [...heartbeats].sort((left, right) => {
    const leftTime = Date.parse(left.last_seen_at);
    const rightTime = Date.parse(right.last_seen_at);
    return rightTime - leftTime;
  })[0];
  if (latestHeartbeat) {
    return {
      service: latestHeartbeat.service,
      environment: latestHeartbeat.environment || "production",
    };
  }
  return {
    service: serviceOptions[0] ?? "",
    environment: "production",
  };
}

function dedupeValues(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

async function pollForVerification({
  projectId,
  service,
  environment,
  previousLastSeenAt,
}: {
  projectId: string;
  service: string;
  environment: string;
  previousLastSeenAt: string | null;
}): Promise<ProjectTelemetryVerification | null> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    if (attempt > 0) {
      await sleep(900);
    }
    const params = new URLSearchParams({ service, environment });
    const response = await fetch(
      `/api/onboarding/projects/${encodeURIComponent(projectId)}/telemetry-verification?${params.toString()}`,
      {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      },
    );
    if (!response.ok) {
      continue;
    }
    const payload = (await response.json()) as ProjectTelemetryVerification;
    if (!payload.last_seen_at) {
      continue;
    }
    if (!previousLastSeenAt || payload.last_seen_at !== previousLastSeenAt || payload.status === "healthy") {
      return payload;
    }
  }
  return null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function formatHeartbeatTimestamp(value: string): string {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(timestamp);
}
