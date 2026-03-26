import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { LandingContactForm } from "@/components/landing-contact-form";

const NAV_ITEMS = [
  { label: "HOW IT WORKS", href: "#about" },
  { label: "PRICING", href: "#pricing" },
  { label: "CONTACT US", href: "#contact" },
];

const SYSTEM_FLOW_STEPS = [
  {
    title: "Detect errors immediately",
    eyebrow: "01. Detect",
    summary:
      "Stimpact watches production in real time and raises the issue as soon as abnormal errors, latency spikes, or failed deploy signals appear.",
    detail:
      "Alerts, traces, logs, and incident signals are correlated into one live case so responders do not lose time stitching the incident together by hand.",
    accent: "real-time error detection",
    points: ["error spikes", "trace anomalies", "deploy failures"],
  },
  {
    title: "Show the team what is happening live",
    eyebrow: "02. Surface",
    summary:
      "The live dashboard exposes the active case through a shared operations panel, incident timeline, and chat-driven coordination workspace.",
    detail:
      "Users can watch the case evolve in the live panel, review evidence, see impacted services, and collaborate in chat while the system keeps updating context.",
    accent: "live panel + chat",
    points: ["live panel", "incident chat", "shared timeline"],
  },
  {
    title: "Draft the repair automatically",
    eyebrow: "03. Repair",
    summary:
      "Once the issue is understood, the platform proposes code changes and recovery actions that match the service state and repository policy.",
    detail:
      "The repair step stays policy-aware so automation can be advisory, semi-automatic, or fully autonomous depending on what the user has enabled.",
    accent: "automatic repair planning",
    points: ["patch candidates", "policy checks", "repo-aware actions"],
  },
  {
    title: "Test every fix in a replica sandbox",
    eyebrow: "04. Sandbox",
    summary:
      "Candidate repairs are executed in a replica sandbox environment that mirrors the real service before anything touches production.",
    detail:
      "This validation step reproduces the issue, applies the fix, and confirms whether the repair actually stabilizes the system without risking the live stack.",
    accent: "replica validation",
    points: ["reproduce incident", "apply patch", "verify recovery"],
  },
  {
    title: "Resolve, commit, and redeploy when allowed",
    eyebrow: "05. Execute",
    summary:
      "If the user enables execution, Stimpact can perform the git operations, move the fix through the repository workflow, and trigger redeployment.",
    detail:
      "Operators still keep visibility through the dashboard while the system opens the repair path, updates the incident record, and closes the loop in production.",
    accent: "git + optional redeploy",
    points: ["git operations", "deployment handoff", "resolved incident state"],
  },
] as const;

const SERVICE_HIGHLIGHTS = [
  {
    title: "Immediate error detection",
    detail: "Flags failures as soon as production behavior shifts.",
  },
  {
    title: "Replica sandbox repair",
    detail: "Tests fixes safely before touching the live environment.",
  },
  {
    title: "Live panel and chat",
    detail: "Lets the team watch, discuss, and guide the response in real time.",
  },
  {
    title: "Git ops and redeploy",
    detail: "Can commit, push, and redeploy when execution is enabled by the user.",
  },
] as const;

const PRICING_PLANS = [
  {
    name: "Basic",
    price: "$15",
    cadence: "per project / month",
    summary:
      "For teams that want real-time detection, a shared dashboard, AI chatbot access, incident chat, and basic investigation on one project.",
    features: [
      "1 integrated project",
      "real-time error detection",
      "live dashboard, AI chatbot, and incident chat",
      "basic incident investigation",
      "shared timeline and evidence view",
      "no automated repair execution",
    ],
    accent: "visibility first",
  },
  {
    name: "Growth",
    price: "$50",
    cadence: "per project / month",
    summary:
      "The full Stimpact suite for one integrated project, including repair generation, replica sandbox validation, and optional execution controls.",
    features: [
      "1 integrated project",
      "full detection and investigation suite",
      "automatic repair drafting",
      "replica sandbox verification",
      "git operations and redeploy when enabled",
    ],
    accent: "full suite",
    featured: true,
  },
  {
    name: "Scale",
    price: "$99",
    cadence: "per month",
    priceNote: "+ $30 / month for each project after 3",
    summary:
      "For teams running Stimpact across multiple integrated projects with shared controls, broader coverage, and centralized operations.",
    features: [
      "multi-project coverage",
      "full suite on every connected project",
      "cross-project policy and approval controls",
      "centralized operations visibility",
      "custom rollout and support options",
    ],
    accent: "multi-project",
  },
] as const;

const WAVE_LAYERS = Array.from({ length: 22 }, (_, index) => index);
const WAVE_PATH_A =
  "M-420 414 C -150 610, 80 214, 318 332 S 618 632, 770 362 1012 112, 1186 252 1466 516, 1920 236";
const WAVE_PATH_B =
  "M-420 392 C -160 560, 86 248, 322 354 S 620 608, 770 346 1014 146, 1190 276 1468 486, 1920 262";
const WAVE_PATH_C =
  "M-420 430 C -170 646, 72 190, 314 314 S 616 654, 772 378 1010 88, 1182 234 1462 536, 1920 214";

export default function Home() {
  return (
    <main className="landing-page-canvas relative min-h-screen overflow-hidden bg-[#030610]">
      <section
        id="home"
        className="landing-reference-shell relative flex min-h-screen w-full flex-col overflow-hidden px-6 py-6 sm:px-8 sm:py-8 lg:px-12 lg:py-10"
      >
        <div className="landing-static-tag absolute bottom-12 right-8 z-20 sm:bottom-14 sm:right-16">
          Self-healing Software
        </div>
        <div className="landing-orb landing-orb-top" />
        <div className="landing-orb landing-orb-right" />
        <div className="landing-orb landing-orb-bottom" />

        <header className="relative z-30 grid items-center gap-6 md:grid-cols-[auto_1fr_auto]">
          <Link href="/" className="inline-flex w-fit items-center gap-3 text-white/90">
            <BrandMark className="h-11 w-11" />
            <span className="text-sm font-semibold tracking-[0.04em]">Stimpact.ai</span>
          </Link>

          <nav
            aria-label="Primary"
            className="hidden items-center justify-center gap-10 md:flex"
          >
            {NAV_ITEMS.map((item) => (
              <Link key={item.label} href={item.href} className="landing-reference-nav-link">
                {item.label}
              </Link>
            ))}
          </nav>

          <Link
            href="/login"
            className="landing-reference-outline-button hidden justify-self-end px-5 py-2 text-sm font-medium text-white/80 sm:inline-flex"
          >
            Login
          </Link>
        </header>

        <AnimatedWaveHero />

        <div className="landing-hero-copy relative z-30 mt-16 max-w-[660px] sm:mt-20 lg:mt-28">
          <h1 className="text-6xl font-semibold tracking-[-0.05em] text-white/94 sm:text-7xl lg:text-[5.35rem]">
            Stimpact.ai
          </h1>
          <p className="mt-5 max-w-[580px] text-lg leading-9 text-white/76 sm:text-[1.45rem]">
            Stimpact brings autonomous incident response, self-healing solutions, and
            sandbox verification into one cinematic control surface for modern reliability
            teams.
          </p>
        </div>

        <div className="relative z-30 mt-auto pt-16">
          <Link
            href="#pricing"
            className="landing-reference-outline-button inline-flex px-6 py-2.5 text-xl font-medium text-white/88"
          >
            sign up
          </Link>
        </div>

      </section>

      <SystemFlowSection />
      <PricingSection />
      <ContactSection />
      <FooterSection />
    </main>
  );
}

function AnimatedWaveHero() {
  return (
    <div className="landing-wave absolute inset-x-0 top-[12%] bottom-[10%] z-10">
      <svg aria-hidden="true" viewBox="0 0 1500 760" preserveAspectRatio="none">
        <defs>
          <linearGradient id="landing-wave-stroke" x1="0%" y1="24%" x2="100%" y2="60%">
            <stop offset="0%" stopColor="var(--vault-blue)" />
            <stop offset="58%" stopColor="var(--vault-orange)" />
            <stop offset="100%" stopColor="var(--vault-gold)" />
          </linearGradient>
          <linearGradient id="landing-wave-fade" x1="0%" y1="50%" x2="100%" y2="50%">
            <stop offset="0%" stopColor="rgba(255,255,255,0)" />
            <stop offset="12%" stopColor="rgba(255,255,255,0.18)" />
            <stop offset="88%" stopColor="rgba(255,255,255,0.2)" />
            <stop offset="100%" stopColor="rgba(255,255,255,0)" />
          </linearGradient>
          <filter id="landing-wave-blur" x="-20%" y="-30%" width="140%" height="160%">
            <feGaussianBlur stdDeviation="18" />
          </filter>
        </defs>

        <g className="landing-wave-ensemble">
          <path
            d={WAVE_PATH_A}
            fill="none"
            stroke="url(#landing-wave-stroke)"
            strokeWidth="42"
            strokeLinecap="round"
            opacity="0.18"
            filter="url(#landing-wave-blur)"
            vectorEffect="non-scaling-stroke"
          >
            <animate
              attributeName="d"
              dur="18s"
              repeatCount="indefinite"
              values={`${WAVE_PATH_A};${WAVE_PATH_B};${WAVE_PATH_C};${WAVE_PATH_A}`}
            />
          </path>

          {WAVE_LAYERS.map((index) => {
            return (
              <g key={index} className="landing-wave-layer">
                <path
                  d={WAVE_PATH_A}
                  transform={`translate(${index * 24 - 260} ${Math.sin(index * 0.55) * 24})`}
                  fill="none"
                  stroke="url(#landing-wave-stroke)"
                  strokeWidth="2.6"
                  strokeLinecap="round"
                  opacity={0.12 + index * 0.026}
                  vectorEffect="non-scaling-stroke"
                  shapeRendering="geometricPrecision"
                >
                  <animate
                    attributeName="d"
                    dur={`${18 + index * 0.12}s`}
                    begin={`${index * -0.28}s`}
                    repeatCount="indefinite"
                    values={`${WAVE_PATH_A};${WAVE_PATH_B};${WAVE_PATH_C};${WAVE_PATH_A}`}
                  />
                </path>
              </g>
            );
          })}

          <path
            d={WAVE_PATH_A}
            fill="none"
            stroke="url(#landing-wave-fade)"
            strokeWidth="1.2"
            strokeLinecap="round"
            opacity="0.62"
            vectorEffect="non-scaling-stroke"
          >
            <animate
              attributeName="d"
              dur="18s"
              repeatCount="indefinite"
              values={`${WAVE_PATH_A};${WAVE_PATH_B};${WAVE_PATH_C};${WAVE_PATH_A}`}
            />
          </path>
        </g>
      </svg>
    </div>
  );
}

function SystemFlowSection() {
  return (
    <section id="about" className="landing-flow-section relative overflow-hidden px-6 py-24 sm:px-8 lg:px-12 lg:py-32">
      <div className="mx-auto max-w-[1280px]">
        <div className="mx-auto max-w-[760px] text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/52">
            System flow
          </p>
          <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white/92 sm:text-5xl">
            One continuous operating loop from signal intake to verified resolution.
          </h2>
          <p className="mx-auto mt-5 max-w-[680px] text-lg leading-8 text-white/62">
            From the first production error to sandbox verification and optional execution,
            the service behaves like one coordinated response loop your team can watch live.
          </p>
        </div>

        <div className="landing-highlight-grid mt-12">
          {SERVICE_HIGHLIGHTS.map((item) => (
            <div key={item.title} className="landing-highlight-card">
              <p className="text-sm font-semibold tracking-tight text-white/90">{item.title}</p>
              <p className="mt-2 text-sm leading-6 text-white/60">{item.detail}</p>
            </div>
          ))}
        </div>

        <div className="landing-flow-timeline relative mt-20">
          {SYSTEM_FLOW_STEPS.map((step, index) => (
            <div
              key={step.title}
              className={`landing-flow-row relative grid gap-6 md:grid-cols-2 md:gap-16 ${
                index % 2 === 0 ? "" : "md:[&>*:first-child]:col-start-2"
              }`}
            >
              <div className="landing-flow-card relative">
                <div className="flex items-center justify-between gap-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-white/52">
                    {step.eyebrow}
                  </p>
                  <span className="landing-flow-accent-pill">{step.accent}</span>
                </div>
                <h3 className="mt-4 text-2xl font-semibold tracking-tight text-white/92">
                  {step.title}
                </h3>
                <p className="mt-4 text-base leading-8 text-white/70">{step.summary}</p>
                <p className="mt-4 text-sm leading-7 text-white/56">{step.detail}</p>
                <div className="mt-5 flex flex-wrap gap-2.5">
                  {step.points.map((point) => (
                    <span key={point} className="landing-flow-point-pill">
                      {point}
                    </span>
                  ))}
                </div>
              </div>

              <div
                className="landing-flow-node"
                aria-hidden="true"
                style={{ ["--flow-node-color" as string]: getFlowNodeColor(index) }}
              >
                <span className="landing-flow-node-inner">{index + 1}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function getFlowNodeColor(index: number) {
  if (index === 0) return "rgba(var(--vault-blue-rgb), 0.95)";
  if (index === SYSTEM_FLOW_STEPS.length - 1) return "rgba(var(--vault-gold-rgb), 0.95)";
  return "rgba(var(--vault-orange-rgb), 0.95)";
}

function PricingSection() {
  return (
    <section id="pricing" className="relative px-6 py-24 sm:px-8 lg:px-12 lg:py-28">
      <div className="mx-auto max-w-[1280px]">
        <div className="mx-auto max-w-[820px] text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/52">
            Pricing
          </p>
          <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white/92 sm:text-5xl">
            Pricing that scales by integrated project, not by passive seats.
          </h2>
          <p className="mx-auto mt-5 max-w-[720px] text-lg leading-8 text-white/62">
            Start with visibility on a single project, unlock the full repair loop on one
            protected service, then scale across multiple projects when your stack grows.
          </p>
        </div>

        <div className="landing-pricing-grid mt-14">
          {PRICING_PLANS.map((plan) => (
            <section
              key={plan.name}
              className={`landing-pricing-card h-full ${plan.featured ? "landing-pricing-card-featured" : ""}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold tracking-[0.08em] text-white/86">
                    {plan.name}
                  </p>
                  <p className="mt-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/48">
                    {plan.accent}
                  </p>
                </div>
                <span className="landing-pricing-pill">{plan.accent}</span>
              </div>

              <div className="mt-8 flex items-end gap-3">
                <span className="text-4xl font-semibold tracking-tight text-white/94 sm:text-5xl">
                  {plan.price}
                </span>
                <span className="pb-1 text-sm text-white/58">{plan.cadence}</span>
              </div>
              {"priceNote" in plan ? (
                <p className="mt-2 text-xs leading-6 text-white/48">{plan.priceNote}</p>
              ) : null}

              <div className="mt-5 flex flex-1 flex-col">
                <p className="text-sm leading-7 text-white/66">{plan.summary}</p>

                <div className="landing-pricing-feature-zone">
                  <div className="landing-pricing-feature-list">
                    {plan.features.map((feature) => (
                      <div key={feature} className="landing-pricing-feature">
                        <span className="landing-pricing-feature-dot" />
                        <span>{feature}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <Link
                  href={`/signup?plan=${plan.name.toLowerCase()}`}
                  className="landing-button-primary inline-flex w-full items-center justify-center rounded-full px-5 py-3 text-sm font-semibold text-white"
                >
                  Start this plan
                </Link>
              </div>
            </section>
          ))}
        </div>
      </div>
    </section>
  );
}

function FooterSection() {
  return (
    <footer className="relative px-6 pb-10 pt-8 sm:px-8 lg:px-12">
      <div className="mx-auto max-w-[1280px] border-t border-white/8 pt-8">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-[520px]">
            <div className="inline-flex items-center gap-3 text-white/88">
              <BrandMark className="h-10 w-10" />
              <span className="text-sm font-semibold tracking-[0.04em]">Stimpact.ai</span>
            </div>
            <p className="mt-4 text-sm leading-7 text-white/58">
              Real-time incident detection, autonomous repair workflows, replica sandbox
              verification, and optional git and redeploy execution for every protected
              project.
            </p>
          </div>

          <div className="grid gap-8 text-sm sm:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/50">
                Platform
              </p>
              <div className="mt-4 space-y-3 text-white/66">
                <p>Detection</p>
                <p>Sandbox repair</p>
                <p>Live panel</p>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/50">
                Execution
              </p>
              <div className="mt-4 space-y-3 text-white/66">
                <p>Git operations</p>
                <p>Deploy controls</p>
                <p>Approval policies</p>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/50">
                Access
              </p>
              <div className="mt-4 space-y-3 text-white/66">
                <Link href="/signup">Get started</Link>
                <Link href="/login">Open live workspace</Link>
                <Link href="#about">View system flow</Link>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 flex flex-col gap-3 border-t border-white/8 pt-6 text-xs text-white/46 sm:flex-row sm:items-center sm:justify-between">
          <p>Basic and Growth cover one integrated project; Scale expands across multiple projects.</p>
          <p>Git operations and redeploy steps only run when explicitly enabled by the user.</p>
        </div>
      </div>
    </footer>
  );
}

function ContactSection() {
  return (
    <section id="contact" className="landing-contact-section relative px-6 py-24 sm:px-8 lg:px-12 lg:py-28">
      <div className="landing-contact-card mx-auto max-w-[1280px]">
        <div className="mx-auto max-w-[760px] text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/52">
            Contact us
          </p>
          <h2 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white/94 sm:text-4xl">
            Talk to us about protecting your stack.
          </h2>
          <p className="mt-4 text-base leading-8 text-white/68">
            Tell us what you want Stimpact.ai to watch, validate, or repair. We will route
            your note directly to connor@stimpact.ai.
          </p>
        </div>

        <div className="mt-10 mx-auto max-w-[760px]">
          <LandingContactForm />
        </div>
      </div>
    </section>
  );
}
