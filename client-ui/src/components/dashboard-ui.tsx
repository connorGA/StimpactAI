import Link from "next/link";
import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <section className="px-1 pb-3 lg:flex lg:items-end lg:justify-between">
      <div>
        <p className="ops-kicker text-[11px] font-semibold uppercase">
          {eyebrow}
        </p>
        <h1 className="ops-title mt-3 max-w-4xl text-3xl font-semibold tracking-tight lg:text-[2.8rem]">
          {title}
        </h1>
        <p className="ops-copy mt-3 max-w-3xl text-sm leading-6">
          {description}
        </p>
        <div className="mt-6 h-px w-24 bg-[linear-gradient(90deg,#171717,rgba(23,23,23,0.08))]" />
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </section>
  );
}

export function StatCard({
  label,
  value,
  detail,
  tone = "blue",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "blue" | "yellow" | "white";
}) {
  const toneClasses =
    tone === "yellow"
      ? "bg-[linear-gradient(180deg,#f6f9ff_0%,#fff1c7_100%)]"
      : tone === "blue"
        ? "bg-[linear-gradient(180deg,#f4f8ff_0%,#e7eefb_100%)]"
        : "bg-[linear-gradient(180deg,#f4f8ff_0%,#e8f0fb_100%)]";

  return (
    <div className={`vault-stat-card rounded-[24px] px-5 py-4 ${toneClasses}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">
        {label}
      </p>
      <p className="mt-3 text-3xl font-semibold text-[#171717]">{value}</p>
      <p className="mt-2 text-sm text-[#746d66]">{detail}</p>
    </div>
  );
}

export function SectionCard({
  title,
  description,
  children,
  aside,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="vault-panel-strong rounded-[24px] p-6">
      <div className="mb-6 flex flex-col gap-3 border-b border-[rgba(17,24,39,0.08)] pb-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="vault-section-title text-[11px] font-semibold uppercase">
            Dashboard module
          </p>
          <h2 className="mt-2 text-xl font-semibold text-[#171717]">{title}</h2>
          {description ? (
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#746d66]">
              {description}
            </p>
          ) : null}
        </div>
        {aside ? <div>{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function PreviewNotice({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <div className="ops-sheet-muted rounded-[22px] p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="inline-flex rounded-full bg-[rgba(23,23,23,0.06)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#745744]">
            Operational note
          </span>
          <h3 className="mt-3 text-base font-semibold text-[#171717]">{title}</h3>
        </div>
        <div className="mt-2 h-2.5 w-2.5 rounded-full bg-[linear-gradient(180deg,#ff8b68,#ff5a2a)]" />
      </div>
      <ul className="mt-4 space-y-2 text-sm leading-6 text-[#746d66]">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function QuickLinkCard({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="vault-panel-strong block rounded-[20px] p-5 transition hover:border-[rgba(255,106,61,0.16)]"
    >
      <p className="vault-section-title text-[11px] font-semibold uppercase">
        Navigate
      </p>
      <h3 className="mt-2 text-lg font-semibold text-[#171717]">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-[#746d66]">{description}</p>
    </Link>
  );
}

export function ProjectSetupState({
  eyebrow = "Project setup required",
  title = "Create your first project to unlock the workspace",
  description = "This workspace is authenticated, but incident, metrics, chat, and automation views stay empty until a project is created and connected through onboarding.",
}: {
  eyebrow?: string;
  title?: string;
  description?: string;
}) {
  return (
    <main className="flex min-h-[calc(100vh-9rem)] items-center">
      <section className="relative mx-auto w-full max-w-[1080px] overflow-hidden rounded-[36px] border border-[rgba(17,24,39,0.08)] bg-[linear-gradient(135deg,rgba(244,248,255,0.98),rgba(233,239,251,0.96)_48%,rgba(255,245,239,0.92)_100%)] px-8 py-10 shadow-[0_24px_64px_rgba(15,23,42,0.08)] lg:px-12 lg:py-14">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(75,107,251,0.14),transparent_24%),radial-gradient(circle_at_78%_18%,rgba(255,106,61,0.16),transparent_24%),radial-gradient(circle_at_72%_82%,rgba(255,178,83,0.14),transparent_22%)]" />
        <div className="relative grid items-center gap-10 lg:grid-cols-[420px_minmax(0,1fr)]">
          <ProjectSetupIllustration />

          <div className="max-w-[560px]">
            <span className="inline-flex rounded-full border border-[rgba(255,106,61,0.16)] bg-white/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#9b4c2f]">
              {eyebrow}
            </span>
            <h1 className="mt-5 text-4xl font-semibold tracking-tight text-[#171717] lg:text-[3.1rem]">
              {title}
            </h1>
            <p className="mt-4 text-base leading-8 text-[#5e6573]">
              {description}
            </p>
            <p className="mt-4 text-base leading-8 text-[#5e6573]">
              Head to onboarding first, create your project, then come back here once setup is complete.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/onboarding"
                className="ops-button inline-flex rounded-full px-5 py-3 text-sm font-semibold text-white transition duration-200 hover:-translate-y-0.5 hover:scale-[1.02] hover:shadow-[0_18px_34px_rgba(255,106,61,0.26)]"
              >
                Go to onboarding
              </Link>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function ProjectSetupIllustration() {
  return (
    <div className="relative mx-auto w-full max-w-[380px]">
      <div className="absolute left-10 top-8 h-24 w-24 rounded-full bg-[radial-gradient(circle,rgba(75,107,251,0.22),transparent_72%)] blur-3xl" />
      <div className="absolute right-0 top-12 h-28 w-28 rounded-full bg-[radial-gradient(circle,rgba(255,106,61,0.16),transparent_72%)] blur-3xl" />

      <div className="relative flex aspect-square items-center justify-center">
        <div className="absolute inset-[12%] rounded-full border border-[rgba(17,24,39,0.06)] bg-[radial-gradient(circle,rgba(255,255,255,0.72),rgba(255,255,255,0.18))]" />

        <FeatureTab
          className="absolute left-[4%] top-[24%] rotate-[-10deg]"
          label="Live"
          tone="blue"
          icon={<PulseGlyph />}
        />
        <FeatureTab
          className="absolute right-[8%] top-[19%] rotate-[10deg]"
          label="Metrics"
          tone="orange"
          icon={<BarsGlyph />}
        />
        <FeatureTab
          className="absolute left-[10%] bottom-[18%] rotate-[8deg]"
          label="Incidents"
          tone="blue"
          icon={<ListGlyph />}
        />
        <FeatureTab
          className="absolute right-[6%] bottom-[24%] rotate-[-8deg]"
          label="Agent"
          tone="orange"
          icon={<SparkMiniGlyph />}
        />

        <svg
          aria-hidden="true"
          viewBox="0 0 320 320"
          className="absolute inset-0 h-full w-full"
          fill="none"
        >
          <path
            d="M82 120c18-18 40-28 65-30 29-2 56 10 82 34"
            stroke="rgba(75,107,251,0.46)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray="8 10"
          />
        </svg>

        <Link
          href="/onboarding"
          className="group relative flex h-[224px] w-[224px] items-center justify-center rounded-full border border-[rgba(255,106,61,0.22)] bg-[linear-gradient(180deg,#ff9b6f_0%,#ff754b_36%,#ff5a2a_100%)] text-white shadow-[0_24px_56px_rgba(255,106,61,0.24)] transition duration-200 hover:scale-[1.02] hover:shadow-[0_28px_64px_rgba(255,106,61,0.3)] focus:outline-none focus-visible:ring-4 focus-visible:ring-[rgba(255,106,61,0.18)]"
          aria-label="Open onboarding"
        >
          <div className="absolute inset-3 rounded-full border border-white/14" />
          <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle_at_50%_24%,rgba(255,255,255,0.26),transparent_30%),radial-gradient(circle_at_50%_82%,rgba(124,45,18,0.16),transparent_42%)]" />
          <div className="relative flex max-w-[164px] -translate-y-2 flex-col items-center text-center">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/52">
              Get Started
            </p>
            <p className="mt-3 text-[2.15rem] font-semibold leading-none">Onboarding</p>
            <p className="mt-4 text-sm leading-6 text-white/72">
              Onboard a project to unlock the workspace.
            </p>
          </div>
        </Link>
      </div>
    </div>
  );
}

function FeatureTab({
  className,
  label,
  tone,
  icon,
}: {
  className: string;
  label: string;
  tone: "blue" | "orange";
  icon: ReactNode;
}) {
  const toneClasses =
    tone === "blue"
      ? "bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(241,246,255,0.94))] text-[#35547d]"
      : "bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(255,246,240,0.96))] text-[#9b4c2f]";

  return (
    <div
      className={`${className} w-[122px] rounded-[22px] border border-[rgba(17,24,39,0.08)] px-4 py-3 shadow-[0_14px_36px_rgba(15,23,42,0.08)] ${toneClasses}`}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em]">
          {label}
        </p>
        <span className="opacity-70">{icon}</span>
      </div>
      <div className="mt-3 h-2 rounded-full bg-black/6" />
      <div className="mt-2 h-2 w-4/5 rounded-full bg-black/5" />
    </div>
  );
}

function PulseGlyph() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M2.5 10h3l1.8-3.5L10 14l2.2-4h5.3" />
    </svg>
  );
}

function BarsGlyph() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 16.5h14" />
      <path d="M6 14V9" />
      <path d="M10 14V5.5" />
      <path d="M14 14v-3" />
    </svg>
  );
}

function ListGlyph() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M6.5 5h9" />
      <path d="M6.5 10h9" />
      <path d="M6.5 15h9" />
      <path d="M3.5 5h.01" />
      <path d="M3.5 10h.01" />
      <path d="M3.5 15h.01" />
    </svg>
  );
}

function SparkMiniGlyph() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m10 3 1.5 4 4 1-4 1.1L10 13l-1.5-3.9-4-1.1 4-1Z" />
    </svg>
  );
}
