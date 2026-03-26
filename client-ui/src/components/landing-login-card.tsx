"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export function LandingLoginCard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });
      const payload = (await response.json()) as {
        error?: { message?: string };
      };
      if (!response.ok) {
        throw new Error(payload.error?.message ?? "Login failed.");
      }
      router.push(searchParams.get("next") || "/live");
      router.refresh();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Login failed.");
      setIsSubmitting(false);
    }
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
        Sign in with your work email to open the live workspace, review incidents, and
        coordinate autonomous response across your team.
      </p>

      <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
            Work email
          </span>
          <input
            type="email"
            name="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
            placeholder="you@company.com"
            autoComplete="email"
            required
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-white/54">
            Password
          </span>
          <input
            type="password"
            name="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="landing-input w-full rounded-[18px] px-4 py-3 text-sm text-white"
            placeholder="Enter your password"
            autoComplete="current-password"
            required
          />
        </label>

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
          {isSubmitting ? "Opening live workspace..." : "Log in to live workspace"}
        </button>
      </form>

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-white/10 pt-4 text-xs text-white/52">
        <span>Protected workspace routes</span>
        <span>Join your team by invite or approved access</span>
      </div>
    </section>
  );
}
