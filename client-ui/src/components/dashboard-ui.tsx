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
