"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type AppShellNavProps = {
  mobile?: boolean;
  compact?: boolean;
};

const navItems = [
  {
    href: "/",
    label: "Live",
    description: "Incidents and uptime",
    icon: "pulse",
  },
  {
    href: "/metrics",
    label: "Metrics",
    description: "Reporting and trends",
    icon: "chart",
  },
  {
    href: "/incidents",
    label: "Incidents",
    description: "Incident explorer",
    icon: "list",
  },
  {
    href: "/control-center",
    label: "Control Center",
    description: "Autonomy and guardrails",
    icon: "shield",
  },
  {
    href: "/chat",
    label: "Agent",
    description: "Inbox and chat focus",
    icon: "spark",
  },
] as const;

export function AppShellNav({
  mobile = false,
  compact = false,
}: AppShellNavProps) {
  const pathname = usePathname();

  if (mobile) {
    return (
      <nav className="flex gap-2 overflow-x-auto lg:hidden">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`vault-nav-link min-w-fit rounded-xl border border-[rgba(17,24,39,0.08)] bg-[linear-gradient(180deg,#f5f8ff,#e8f0fb)] px-4 py-2 text-sm font-medium shadow-[0_8px_20px_rgba(15,23,42,0.04)] transition ${
                isActive ? "vault-nav-link-active" : ""
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    );
  }

  return (
    <div className="hidden h-full flex-col justify-between lg:flex">
      <div>
        <nav className="space-y-1.5">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`vault-sidebar-link vault-nav-link block -mx-2 px-4 py-3 transition ${
                  isActive ? "vault-nav-link-active" : ""
                }`}
              >
                <div className={`flex items-center justify-between gap-3 ${compact ? "justify-center" : ""}`}>
                  <div className={compact ? "hidden" : "block"}>
                    <p className="text-sm font-semibold">{item.label}</p>
                    <p className="mt-1 text-xs opacity-70">{item.description}</p>
                  </div>
                  {compact ? (
                    <span className="opacity-80">
                      <NavIcon icon={item.icon} />
                    </span>
                  ) : (
                    <span className="opacity-60">
                      <NavIcon icon={item.icon} />
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}

function NavIcon({
  icon,
}: {
  icon: (typeof navItems)[number]["icon"];
}) {
  if (icon === "pulse") {
    return (
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M2.5 10h3l1.8-3.5L10 14l2.2-4h5.3" />
      </svg>
    );
  }

  if (icon === "chart") {
    return (
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
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

  if (icon === "list") {
    return (
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
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

  if (icon === "shield") {
    return (
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M10 2.8 15.5 5v4.4c0 3.6-2.2 6.1-5.5 7.8-3.3-1.7-5.5-4.2-5.5-7.8V5L10 2.8Z" />
      </svg>
    );
  }

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 3.5 11.9 7.3l4.1.6-3 2.9.7 4.1-3.7-2-3.7 2 .7-4.1-3-2.9 4.1-.6L10 3.5Z" />
    </svg>
  );
}
