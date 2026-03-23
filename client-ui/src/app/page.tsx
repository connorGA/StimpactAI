import Link from "next/link";

const NAV_ITEMS = [
  { label: "HOME", href: "#home" },
  { label: "ABOUT US", href: "#about" },
  { label: "GALLERY", href: "#gallery" },
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
    name: "Starter",
    price: "$299",
    cadence: "per project / month",
    summary: "Best for teams that want live incident visibility and guided response on a single integrated project.",
    features: [
      "1 integrated project",
      "real-time error detection",
      "live panel and incident chat",
      "sandbox repair validation",
      "human approval before execution",
    ],
    accent: "launch safely",
  },
  {
    name: "Growth",
    price: "$899",
    cadence: "per project / month",
    summary: "For production teams that want autonomous repair loops, richer visibility, and optional repository execution.",
    features: [
      "up to 3 environments per project",
      "automatic repair drafting",
      "replica sandbox verification",
      "git operations when enabled",
      "optional redeploy triggers",
    ],
    accent: "most popular",
    featured: true,
  },
  {
    name: "Scale",
    price: "$2,400+",
    cadence: "per project / month",
    summary: "For critical systems needing deeper policy controls, enterprise workflows, and higher-volume operational coverage.",
    features: [
      "custom environment mappings",
      "advanced policy and approval rules",
      "multi-team coordination surfaces",
      "enterprise deployment integrations",
      "priority onboarding and support",
    ],
    accent: "custom control",
  },
] as const;

const WAVE_LAYERS = Array.from({ length: 22 }, (_, index) => index);
const WAVE_PATH_A =
  "M-180 414 C 20 610, 162 214, 338 332 S 618 632, 770 362 1012 112, 1186 252 1406 516, 1660 236";
const WAVE_PATH_B =
  "M-180 392 C 18 560, 168 248, 342 354 S 620 608, 770 346 1014 146, 1190 276 1408 486, 1660 262";
const WAVE_PATH_C =
  "M-180 430 C 12 646, 156 190, 334 314 S 616 654, 772 378 1010 88, 1182 234 1402 536, 1660 214";

export default function Home() {
  return (
    <main className="landing-page-canvas relative min-h-screen overflow-hidden bg-[#030610]">
      <section
        id="home"
        className="landing-reference-shell relative flex min-h-screen w-full flex-col overflow-hidden px-6 py-6 sm:px-8 sm:py-8 lg:px-12 lg:py-10"
      >
        <div className="landing-dot-matrix absolute bottom-12 right-10 z-20 h-12 w-44 sm:bottom-14 sm:right-16" />
        <div className="landing-orb landing-orb-left" />
        <div className="landing-orb landing-orb-top" />
        <div className="landing-orb landing-orb-right" />
        <div className="landing-orb landing-orb-bottom" />

        <header className="relative z-30 grid items-center gap-6 md:grid-cols-[auto_1fr_auto]">
          <Link href="/" className="inline-flex w-fit items-center gap-3 text-white/90">
            <BrandMark />
            <span className="text-sm font-semibold tracking-[0.04em]">Stimpact</span>
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
            href="/live"
            className="landing-reference-outline-button hidden justify-self-end px-5 py-2 text-sm font-medium text-white/80 sm:inline-flex"
          >
            learn more
          </Link>
        </header>

        <AnimatedWaveHero />

        <div className="relative z-30 mt-16 max-w-[520px] sm:mt-20 lg:mt-28">
          <h1 className="text-5xl font-semibold tracking-[-0.04em] text-white/92 sm:text-6xl lg:text-[4.15rem]">
            Landing Page
          </h1>
          <p className="mt-4 max-w-[420px] text-sm leading-6 text-white/42 sm:text-[15px]">
            Stimpact brings autonomous incident response, live operations, and sandbox
            verification into one cinematic control surface for modern reliability teams.
          </p>
        </div>

        <div className="relative z-30 mt-auto pt-16">
          <Link
            href="/onboarding"
            className="landing-reference-outline-button inline-flex px-6 py-2.5 text-xl font-medium text-white/88"
          >
            sign up
          </Link>
        </div>

      </section>

      <SystemFlowSection />
      <PricingSection />
      <FooterSection />

      <div id="gallery" className="sr-only">
        Gallery section anchor
      </div>
      <div id="contact" className="sr-only">
        Contact section anchor
      </div>
    </main>
  );
}

function BrandMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 32 32" className="h-9 w-9 text-white/86">
      <g fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M16 3.75 27.5 10.5V21.5L16 28.25 4.5 21.5V10.5L16 3.75Z" opacity="0.88" />
        <path d="M16 8.5 23 12.5V19.5L16 23.5 9 19.5V12.5L16 8.5Z" opacity="0.92" />
        <path d="M11.2 16h9.6" opacity="0.55" />
      </g>
    </svg>
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
                  transform={`translate(${index * 24 - 180} ${Math.sin(index * 0.55) * 24})`}
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
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/42">
            System flow
          </p>
          <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white/92 sm:text-5xl">
            One continuous operating loop from signal intake to verified resolution.
          </h2>
          <p className="mx-auto mt-5 max-w-[680px] text-base leading-7 text-white/50">
            From the first production error to sandbox verification and optional execution,
            the service behaves like one coordinated response loop your team can watch live.
          </p>
        </div>

        <div className="landing-highlight-grid mt-12">
          {SERVICE_HIGHLIGHTS.map((item) => (
            <div key={item.title} className="landing-highlight-card">
              <p className="text-sm font-semibold tracking-tight text-white/90">{item.title}</p>
              <p className="mt-2 text-sm leading-6 text-white/48">{item.detail}</p>
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
                  <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-white/42">
                    {step.eyebrow}
                  </p>
                  <span className="landing-flow-accent-pill">{step.accent}</span>
                </div>
                <h3 className="mt-4 text-2xl font-semibold tracking-tight text-white/92">
                  {step.title}
                </h3>
                <p className="mt-4 text-base leading-7 text-white/58">{step.summary}</p>
                <p className="mt-4 text-sm leading-7 text-white/42">{step.detail}</p>
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
    <section className="relative px-6 py-24 sm:px-8 lg:px-12 lg:py-28">
      <div className="mx-auto max-w-[1280px]">
        <div className="mx-auto max-w-[820px] text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/42">
            Pricing
          </p>
          <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white/92 sm:text-5xl">
            Pricing that scales by integrated project, not by passive seats.
          </h2>
          <p className="mx-auto mt-5 max-w-[720px] text-base leading-7 text-white/50">
            Each connected project gets its own live detection, sandbox validation, and
            repair workflow. Teams pay for the projects Stimpact is actively protecting.
          </p>
        </div>

        <div className="landing-pricing-grid mt-14">
          {PRICING_PLANS.map((plan) => (
            <section
              key={plan.name}
              className={`landing-pricing-card ${plan.featured ? "landing-pricing-card-featured" : ""}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold tracking-[0.08em] text-white/86">
                    {plan.name}
                  </p>
                  <p className="mt-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/38">
                    {plan.accent}
                  </p>
                </div>
                <span className="landing-pricing-pill">{plan.accent}</span>
              </div>

              <div className="mt-8 flex items-end gap-3">
                <span className="text-4xl font-semibold tracking-tight text-white/94 sm:text-5xl">
                  {plan.price}
                </span>
                <span className="pb-1 text-sm text-white/46">{plan.cadence}</span>
              </div>

              <p className="mt-5 text-sm leading-7 text-white/56">{plan.summary}</p>

              <div className="mt-8 space-y-3">
                {plan.features.map((feature) => (
                  <div key={feature} className="landing-pricing-feature">
                    <span className="landing-pricing-feature-dot" />
                    <span>{feature}</span>
                  </div>
                ))}
              </div>

              <Link
                href="/onboarding"
                className={`mt-8 inline-flex w-full items-center justify-center rounded-full px-5 py-3 text-sm font-semibold ${
                  plan.featured
                    ? "landing-button-primary text-white"
                    : "landing-reference-outline-button text-white/88"
                }`}
              >
                Start this plan
              </Link>
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
              <BrandMark />
              <span className="text-sm font-semibold tracking-[0.04em]">Stimpact</span>
            </div>
            <p className="mt-4 text-sm leading-7 text-white/46">
              Real-time incident detection, autonomous repair workflows, replica sandbox
              verification, and optional git and redeploy execution for every protected
              project.
            </p>
          </div>

          <div className="grid gap-8 text-sm sm:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/40">
                Platform
              </p>
              <div className="mt-4 space-y-3 text-white/56">
                <p>Detection</p>
                <p>Sandbox repair</p>
                <p>Live panel</p>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/40">
                Execution
              </p>
              <div className="mt-4 space-y-3 text-white/56">
                <p>Git operations</p>
                <p>Deploy controls</p>
                <p>Approval policies</p>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/40">
                Access
              </p>
              <div className="mt-4 space-y-3 text-white/56">
                <Link href="/onboarding">Get started</Link>
                <Link href="/live">Open live workspace</Link>
                <Link href="#about">View system flow</Link>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 flex flex-col gap-3 border-t border-white/8 pt-6 text-xs text-white/34 sm:flex-row sm:items-center sm:justify-between">
          <p>Pricing is billed per integrated project under active protection.</p>
          <p>Execution steps like git push or redeploy only run when explicitly enabled.</p>
        </div>
      </div>
    </footer>
  );
}
