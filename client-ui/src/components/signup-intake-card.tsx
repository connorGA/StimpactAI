"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const PLAN_LABELS: Record<string, string> = {
  basic: "Basic",
  growth: "Growth",
  scale: "Scale",
};

const SCALE_BASE_PRICE = 99;
const SCALE_INCLUDED_PROJECTS = 3;
const SCALE_ADDITIONAL_PROJECT_PRICE = 30;

function slugifyWorkspaceName(value: string): string {
  const normalized = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");

  return normalized || "workspace";
}

export function SignupIntakeCard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get("invite");
  const selectedPlan = useMemo(() => {
    const rawPlan = (searchParams.get("plan") ?? "growth").toLowerCase();
    return PLAN_LABELS[rawPlan] ? rawPlan : "growth";
  }, [searchParams]);
  const isScalePlan = selectedPlan === "scale";
  const [mode, setMode] = useState<"create" | "join">(inviteToken ? "join" : "create");
  const [planMenuOpen, setPlanMenuOpen] = useState(false);
  const planMenuRef = useRef<HTMLDivElement | null>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [organizationName, setOrganizationName] = useState("Acme");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [projectCount, setProjectCount] = useState(selectedPlan === "scale" ? "4" : "1");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const organizationSlug = useMemo(
    () => slugifyWorkspaceName(organizationName),
    [organizationName],
  );
  const scaleProjectCount = useMemo(() => {
    const parsed = Number.parseInt(projectCount, 10);
    return Number.isFinite(parsed) ? Math.max(parsed, 1) : 1;
  }, [projectCount]);
  const scaleAdditionalProjects = Math.max(
    scaleProjectCount - SCALE_INCLUDED_PROJECTS,
    0,
  );
  const scaleMonthlyTotal =
    SCALE_BASE_PRICE +
    scaleAdditionalProjects * SCALE_ADDITIONAL_PROJECT_PRICE;
  const passwordsMatch = password === confirmPassword;

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!planMenuRef.current?.contains(event.target as Node)) {
        setPlanMenuOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setPlanMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  function updateSelectedPlan(plan: string) {
    const normalizedPlan = plan.toLowerCase();
    const params = new URLSearchParams(searchParams.toString());
    params.set("plan", normalizedPlan);
    router.replace(`/signup?${params.toString()}`);
    if (normalizedPlan !== "scale") {
      setProjectCount("1");
    }
    setPlanMenuOpen(false);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setStatusMessage(null);
    setErrorMessage(null);
    if ((mode === "create" || inviteToken) && !passwordsMatch) {
      setErrorMessage("Passwords must match.");
      setIsSubmitting(false);
      return;
    }
    try {
      if (inviteToken) {
        const response = await fetch("/api/auth/accept-invite", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            invite_token: inviteToken,
            full_name: fullName,
            password,
          }),
        });
        const payload = (await response.json()) as { error?: { message?: string } };
        if (!response.ok) {
          throw new Error(payload.error?.message ?? "Invite acceptance failed.");
        }
        router.push("/live");
        router.refresh();
        return;
      }

      if (mode === "join") {
        const response = await fetch("/api/auth/access-requests", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            organization_slug: organizationSlug,
            full_name: fullName,
            email,
          }),
        });
        const payload = (await response.json()) as { error?: { message?: string } };
        if (!response.ok) {
          throw new Error(payload.error?.message ?? "Access request failed.");
        }
        setStatusMessage(
          "Access request sent. An owner or admin can approve it and share an invite token.",
        );
        setIsSubmitting(false);
        return;
      }

      const response = await fetch("/api/auth/signup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          plan: selectedPlan,
          organization_name: organizationName,
          organization_slug: organizationSlug,
          full_name: fullName,
          email,
          password,
        }),
      });
      const payload = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        throw new Error(payload.error?.message ?? "Signup failed.");
      }
      router.push("/onboarding");
      router.refresh();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Signup failed.");
      setIsSubmitting(false);
    }
  }

  return (
    <section className="landing-auth-card relative overflow-hidden rounded-[30px] p-6 shadow-[0_30px_80px_rgba(2,6,23,0.24)] sm:p-7 lg:min-h-[860px]">
      <div className="absolute inset-x-12 top-0 h-px bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.78),rgba(255,255,255,0))]" />
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/54">
            Get started
          </p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white">
            Create your Stimpact.ai workspace
          </h2>
        </div>
        <span className="landing-status-chip rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-white">
          {PLAN_LABELS[selectedPlan]}
        </span>
      </div>

      <p className="mt-3 text-sm leading-6 text-white/70">
        {inviteToken
          ? "Accept the invite to join your company workspace and continue into protected onboarding."
          : mode === "create"
            ? "Choose your starting plan and create the workspace that will own your protected projects."
            : "Request access to an existing team if your company has already created a Stimpact.ai workspace."}
      </p>

      <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
        {!inviteToken ? (
          <div className="grid grid-cols-2 gap-2 rounded-[18px] border border-white/10 bg-white/4 p-1">
            <button
              type="button"
              onClick={() => setMode("create")}
              className={`rounded-[14px] px-3 py-2 text-sm font-semibold transition ${
                mode === "create" ? "bg-white/12 text-white" : "text-white/58"
              }`}
            >
              Create team
            </button>
            <button
              type="button"
              onClick={() => setMode("join")}
              className={`rounded-[14px] px-3 py-2 text-sm font-semibold transition ${
                mode === "join" ? "bg-white/12 text-white" : "text-white/58"
              }`}
            >
              Join existing team
            </button>
          </div>
        ) : null}

        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
            {inviteToken ? "Invite flow" : "Selected plan"}
          </span>
          {inviteToken ? (
            <div className="rounded-[18px] border border-white/10 bg-white/4 px-4 py-3 text-sm text-white/74">
              Joining a workspace by invite token
            </div>
          ) : mode === "join" ? (
            <div className="rounded-[18px] border border-white/10 bg-white/4 px-4 py-3 text-sm text-white/74">
              You&apos;ll join your team&apos;s existing workspace and inherit its plan settings.
            </div>
          ) : (
            <div ref={planMenuRef} className="landing-select-shell">
              <button
                type="button"
                onClick={() => setPlanMenuOpen((open) => !open)}
                aria-haspopup="listbox"
                aria-expanded={planMenuOpen}
                className="landing-input landing-select-input flex w-full items-center justify-between rounded-[18px] px-4 py-3 text-left text-sm text-white"
              >
                <span>{PLAN_LABELS[selectedPlan]}</span>
              </button>
              <span className="landing-select-icon" aria-hidden="true">
                <svg
                  viewBox="0 0 20 20"
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="m5.5 7.75 4.5 4.5 4.5-4.5" />
                </svg>
              </span>
              {planMenuOpen ? (
                <div
                  role="listbox"
                  className="absolute left-0 right-0 top-[calc(100%+0.55rem)] z-30 overflow-hidden rounded-[20px] border border-white/12 bg-[linear-gradient(180deg,rgba(20,27,46,0.98),rgba(13,18,32,0.98))] p-2 shadow-[0_24px_64px_rgba(2,6,23,0.42)] backdrop-blur-xl"
                >
                  {Object.entries(PLAN_LABELS).map(([value, label]) => {
                    const active = selectedPlan === value;
                    return (
                      <button
                        key={value}
                        type="button"
                        role="option"
                        aria-selected={active}
                        onClick={() => updateSelectedPlan(value)}
                        className={`flex w-full items-center justify-between rounded-[14px] px-3 py-3 text-sm transition ${
                          active
                            ? "bg-white/10 text-white"
                            : "text-white/72 hover:bg-white/6 hover:text-white"
                        }`}
                      >
                        <span>{label}</span>
                        {active ? (
                          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
                            Selected
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          )}
        </label>

        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
            Full name
          </span>
          <input
            type="text"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
            placeholder="Your name"
            autoComplete="name"
            required
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
            {mode === "join" && !inviteToken ? "Existing team name" : "Team name"}
          </span>
          <input
            type="text"
            value={organizationName}
            onChange={(event) => setOrganizationName(event.target.value)}
            className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
            placeholder="Acme"
            autoComplete="organization"
            required
          />
        </label>

        {!inviteToken ? (
          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
              Work email
            </span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
              placeholder="you@company.com"
              autoComplete="email"
              required
            />
          </label>
        ) : null}

        {(mode === "create" || inviteToken) ? (
          <>
            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
                Password
              </span>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="landing-input w-full rounded-[18px] px-4 py-3 pr-12 text-sm text-white"
                  placeholder="Create a secure password"
                  autoComplete="new-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute right-3 top-1/2 inline-flex -translate-y-1/2 items-center justify-center text-white/54 transition hover:text-white/82"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  <svg
                    viewBox="0 0 20 20"
                    className="h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    {showPassword ? (
                      <>
                        <path d="M1.5 10s3-5.5 8.5-5.5S18.5 10 18.5 10s-3 5.5-8.5 5.5S1.5 10 1.5 10Z" />
                        <circle cx="10" cy="10" r="2.4" />
                      </>
                    ) : (
                      <>
                        <path d="M2.5 2.5 17.5 17.5" />
                        <path d="M8.8 4.7A9.4 9.4 0 0 1 10 4.5c5.5 0 8.5 5.5 8.5 5.5a15.1 15.1 0 0 1-2.7 3.5" />
                        <path d="M5.1 5.2A15.3 15.3 0 0 0 1.5 10s3 5.5 8.5 5.5c1.4 0 2.6-.3 3.7-.8" />
                      </>
                    )}
                  </svg>
                </button>
              </div>
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
                Confirm password
              </span>
              <div className="relative">
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  className="landing-input w-full rounded-[18px] px-4 py-3 pr-12 text-sm text-white"
                  placeholder="Re-enter your password"
                  autoComplete="new-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword((value) => !value)}
                  className="absolute right-3 top-1/2 inline-flex -translate-y-1/2 items-center justify-center text-white/54 transition hover:text-white/82"
                  aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                >
                  <svg
                    viewBox="0 0 20 20"
                    className="h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    {showConfirmPassword ? (
                      <>
                        <path d="M1.5 10s3-5.5 8.5-5.5S18.5 10 18.5 10s-3 5.5-8.5 5.5S1.5 10 1.5 10Z" />
                        <circle cx="10" cy="10" r="2.4" />
                      </>
                    ) : (
                      <>
                        <path d="M2.5 2.5 17.5 17.5" />
                        <path d="M8.8 4.7A9.4 9.4 0 0 1 10 4.5c5.5 0 8.5 5.5 8.5 5.5a15.1 15.1 0 0 1-2.7 3.5" />
                        <path d="M5.1 5.2A15.3 15.3 0 0 0 1.5 10s3 5.5 8.5 5.5c1.4 0 2.6-.3 3.7-.8" />
                      </>
                    )}
                  </svg>
                </button>
              </div>
              {confirmPassword && !passwordsMatch ? (
                <p className="mt-2 text-xs leading-5 text-[rgba(255,106,61,0.88)]">
                  Passwords do not match yet.
                </p>
              ) : null}
            </label>
          </>
        ) : null}

        {mode === "create" && isScalePlan ? (
          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
              Projects to protect first
            </span>
            <input
              type="number"
              min="1"
              value={projectCount}
              onChange={(event) => setProjectCount(event.target.value)}
              className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
            />
            <div className="mt-3 rounded-[18px] border border-white/10 bg-white/4 px-4 py-3 text-sm text-white/68">
              <div className="flex items-center justify-between gap-4">
                <span>Estimated monthly cost</span>
                <span className="text-base font-semibold text-white/92">
                  ${scaleMonthlyTotal}/month
                </span>
              </div>
              <p className="mt-2 text-xs leading-6 text-white/52">
                ${SCALE_BASE_PRICE}/month includes {SCALE_INCLUDED_PROJECTS} projects.
                {scaleAdditionalProjects > 0
                  ? ` + $${SCALE_ADDITIONAL_PROJECT_PRICE}/month x ${scaleAdditionalProjects} additional project${scaleAdditionalProjects === 1 ? "" : "s"}.`
                  : " No additional project charges yet."}
              </p>
            </div>
          </label>
        ) : (
          <div className="rounded-[18px] border border-white/10 bg-white/4 px-4 py-3 text-sm text-white/62">
            Includes `1 protected project` on the {PLAN_LABELS[selectedPlan]} plan.
          </div>
        )}

        {statusMessage ? (
          <div className="rounded-[18px] border border-[rgba(75,107,251,0.24)] bg-[rgba(75,107,251,0.08)] px-4 py-3 text-sm text-white/80">
            {statusMessage}
          </div>
        ) : null}

        {errorMessage ? (
          <div className="rounded-[18px] border border-[rgba(255,106,61,0.24)] bg-[rgba(255,106,61,0.08)] px-4 py-3 text-sm text-white/80">
            {errorMessage}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={isSubmitting}
          className="landing-button-primary inline-flex w-full items-center justify-center rounded-[18px] px-4 py-3 text-sm font-semibold text-white transition disabled:cursor-wait disabled:opacity-80"
        >
          {isSubmitting
            ? inviteToken
              ? "Joining workspace..."
              : mode === "join"
                ? "Sending request..."
                : "Opening onboarding..."
            : inviteToken
              ? "Accept invite"
              : mode === "join"
                ? "Request access"
                : "Continue to onboarding"}
        </button>
      </form>

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-white/10 pt-4 text-xs text-white/52">
        <span>Plan can be changed later</span>
        <span>Project-based billing</span>
      </div>
    </section>
  );
}
