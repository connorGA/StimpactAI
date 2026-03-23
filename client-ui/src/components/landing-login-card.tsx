"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function LandingLoginCard() {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    router.push("/live");
  }

  return (
    <section className="landing-login-panel relative overflow-hidden rounded-[28px] p-6 text-left shadow-[0_30px_80px_rgba(15,23,42,0.22)]">
      <div className="absolute inset-x-10 top-0 h-px bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.8),rgba(255,255,255,0))]" />
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/58">
            Team access
          </p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white">
            Log in to your existing workspace
          </h2>
        </div>
        <div className="landing-status-chip rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-white">
          Secure
        </div>
      </div>

      <p className="mt-3 text-sm leading-6 text-white/72">
        Use your team account to open the live workspace, review incidents, and coordinate
        autonomous response.
      </p>

      <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
            Team workspace
          </span>
          <input
            type="text"
            name="workspace"
            defaultValue="stimpact-prod"
            className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
            placeholder="your-team"
            autoComplete="organization"
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
            Work email
          </span>
          <input
            type="email"
            name="email"
            defaultValue="ops@stimpact.ai"
            className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
            placeholder="you@company.com"
            autoComplete="email"
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
            Password
          </span>
          <input
            type="password"
            name="password"
            defaultValue="password"
            className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
            placeholder="Enter your password"
            autoComplete="current-password"
          />
        </label>

        <button
          type="submit"
          disabled={isSubmitting}
          className="landing-button-primary inline-flex w-full items-center justify-center rounded-[18px] px-4 py-3 text-sm font-semibold text-white transition disabled:cursor-wait disabled:opacity-80"
        >
          {isSubmitting ? "Opening live workspace..." : "Log in to live workspace"}
        </button>
      </form>

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-white/10 pt-4 text-xs text-white/52">
        <span>SSO-ready team access</span>
        <span>Protected workspace routes</span>
      </div>
    </section>
  );
}
