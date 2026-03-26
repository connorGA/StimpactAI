import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { SignupIntakeCard } from "@/components/signup-intake-card";

type SignupPageProps = {
  searchParams: Promise<{
    plan?: string;
  }>;
};

const VALID_PLANS = new Set(["basic", "growth", "scale"]);

export default async function SignupPage({ searchParams }: SignupPageProps) {
  const params = await searchParams;
  const selectedPlan = (params.plan ?? "growth").toLowerCase();
  const activePlan = VALID_PLANS.has(selectedPlan) ? selectedPlan : "growth";

  return (
    <main className="landing-auth-page min-h-screen px-6 py-8 sm:px-8 lg:px-12">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-[1280px] flex-col">
        <header className="flex items-center justify-between gap-4">
          <Link href="/" className="inline-flex items-center gap-3 text-white/90">
            <BrandMark className="h-11 w-11" />
            <span className="text-sm font-semibold tracking-[0.04em]">Stimpact.ai</span>
          </Link>
          <Link
            href="/login"
            className="landing-reference-outline-button inline-flex px-5 py-2 text-sm font-medium text-white/88"
          >
            Login
          </Link>
        </header>

        <section className="grid flex-1 items-center gap-10 py-10 lg:grid-cols-[minmax(0,1.05fr)_460px] lg:items-start">
          <div className="lg:pt-24">
            <div className="max-w-[660px]">
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/40">
                Sign up
              </p>
              <h1 className="mt-4 text-5xl font-semibold tracking-[-0.04em] text-white/94 sm:text-6xl">
                Create a new team or join the one your company already runs.
              </h1>
              <p className="mt-6 max-w-[600px] text-base leading-8 text-white/52">
                Choose the plan that fits your stack, create the workspace for your first
                protected project, or request access to an existing team before moving into
                guided onboarding.
              </p>
              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                <div
                  className={`landing-highlight-card ${
                    activePlan === "basic"
                      ? "landing-highlight-card-active"
                      : ""
                  }`}
                >
                  <p className="text-sm font-semibold tracking-tight text-white/90">Basic</p>
                  <p
                    className={`mt-2 text-sm leading-6 ${
                      activePlan === "basic" ? "text-white/72" : "text-white/48"
                    }`}
                  >
                    Detection, dashboard, chat, investigation.
                  </p>
                </div>
                <div
                  className={`landing-highlight-card ${
                    activePlan === "growth"
                      ? "landing-highlight-card-active"
                      : ""
                  }`}
                >
                  <p className="text-sm font-semibold tracking-tight text-white/90">Growth</p>
                  <p
                    className={`mt-2 text-sm leading-6 ${
                      activePlan === "growth" ? "text-white/72" : "text-white/48"
                    }`}
                  >
                    Full repair suite for one integrated project.
                  </p>
                </div>
                <div
                  className={`landing-highlight-card ${
                    activePlan === "scale"
                      ? "landing-highlight-card-active"
                      : ""
                  }`}
                >
                  <p className="text-sm font-semibold tracking-tight text-white/90">Scale</p>
                  <p
                    className={`mt-2 text-sm leading-6 ${
                      activePlan === "scale" ? "text-white/72" : "text-white/48"
                    }`}
                  >
                    Full suite across multiple connected projects.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="lg:justify-self-end">
            <SignupIntakeCard />
          </div>
        </section>
      </div>
    </main>
  );
}
