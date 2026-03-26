import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { LandingLoginCard } from "@/components/landing-login-card";

export default function LoginPage() {
  return (
    <main className="landing-auth-page min-h-screen px-6 py-8 sm:px-8 lg:px-12">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-[1280px] flex-col">
        <header className="flex items-center justify-between gap-4">
          <Link href="/" className="inline-flex items-center gap-3 text-white/90">
            <BrandMark className="h-11 w-11" />
            <span className="text-sm font-semibold tracking-[0.04em]">Stimpact.ai</span>
          </Link>
          <Link
            href="/signup"
            className="landing-reference-outline-button inline-flex px-5 py-2 text-sm font-medium text-white/88"
          >
            Sign up
          </Link>
        </header>

        <section className="grid flex-1 items-center gap-10 py-10 lg:grid-cols-[minmax(0,1.05fr)_420px]">
          <div className="max-w-[620px]">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/40">
              Login
            </p>
            <h1 className="mt-4 text-5xl font-semibold tracking-[-0.04em] text-white/94 sm:text-6xl">
              Access your live incident workspace.
            </h1>
            <p className="mt-6 max-w-[560px] text-base leading-8 text-white/52">
              Sign in to review active incidents, watch autonomous repair progress, inspect
              sandbox verification runs, and coordinate your team from the live panel and
              incident chat.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <span className="landing-flow-point-pill">live dashboard</span>
              <span className="landing-flow-point-pill">incident chat</span>
              <span className="landing-flow-point-pill">sandbox verification</span>
            </div>
          </div>

          <div className="lg:justify-self-end">
            <LandingLoginCard />
          </div>
        </section>
      </div>
    </main>
  );
}
