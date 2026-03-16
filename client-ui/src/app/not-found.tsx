import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col items-center justify-center px-6 py-16 text-center">
      <section className="vault-panel w-full rounded-[32px] px-8 py-10">
        <p className="text-sm font-semibold uppercase tracking-[0.24em] text-[#5a7393]">
          Stimpact AI
        </p>
        <div className="vault-accent-rule mx-auto mt-4 w-40" />
        <h1 className="mt-5 text-4xl font-bold tracking-tight text-[#17385d]">
          Incident not found
        </h1>
        <p className="mt-4 max-w-xl text-sm leading-6 text-[#5a7291]">
          The requested incident could not be loaded from the agent platform. It
          may have been removed, or the identifier may be invalid.
        </p>
        <Link
          href="/"
          className="vault-button-primary mt-8 inline-flex rounded-2xl px-4 py-2 text-sm font-semibold text-white transition"
        >
          Return to dashboard
        </Link>
      </section>
    </main>
  );
}
