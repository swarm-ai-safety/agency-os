export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden grid-bg">
      {/* Gradient orbs */}
      <div className="absolute top-1/4 left-1/4 h-96 w-96 rounded-full bg-red-500/5 blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 h-96 w-96 rounded-full bg-[var(--color-accent)]/5 blur-3xl" />

      <div className="relative mx-auto max-w-4xl px-6 pt-32 pb-20 text-center">
        <div className="animate-fade-in-up">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[var(--color-accent)]/20 bg-[var(--color-accent)]/10 px-4 py-1.5 text-xs text-[var(--color-accent)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
            OpenAI-compatible API &mdash; switch in one line
          </div>
        </div>

        <h1 className="animate-fade-in-up-delay-1 text-5xl sm:text-6xl md:text-7xl font-extrabold tracking-tight leading-[1.08]">
          Smart LLM routing
          <br />
          that saves you
          <br />
          <span className="text-[var(--color-accent)]">30&ndash;80% on AI costs</span>
        </h1>

        <p className="animate-fade-in-up-delay-2 mt-6 text-lg sm:text-xl text-[var(--color-text-muted)] max-w-2xl mx-auto leading-relaxed">
          One API for every model. Automatic routing to the cheapest provider
          that meets your quality bar. Real-time cost tracking, built-in
          caching, and hard budget limits &mdash; so your AI spend never
          surprises you.
        </p>

        <div className="animate-fade-in-up-delay-2 mt-8 grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-2xl mx-auto text-left">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
            <div className="text-2xl font-extrabold text-[var(--color-accent)] tabular-nums">30-80%</div>
            <div className="text-xs text-[var(--color-text-muted)]">Cost savings with smart model routing</div>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
            <div className="text-2xl font-extrabold text-[var(--color-accent)] tabular-nums">&lt;50ms</div>
            <div className="text-xs text-[var(--color-text-muted)]">Routing overhead per request</div>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
            <div className="text-2xl font-extrabold text-[var(--color-accent)] tabular-nums">1 line</div>
            <div className="text-xs text-[var(--color-text-muted)]">To switch from OpenAI &mdash; change your base URL</div>
          </div>
        </div>

        <div className="animate-fade-in-up-delay-3 mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="/signup"
            className="w-full sm:w-auto rounded-xl bg-[var(--color-accent)] px-8 py-3.5 text-base font-semibold text-black hover:brightness-110 transition-all"
          >
            Get Your API Key
          </a>
          <a
            href="#problem"
            className="w-full sm:w-auto rounded-xl border border-[var(--color-border)] px-8 py-3.5 text-base font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text-muted)] transition-all"
          >
            See How It Works
          </a>
        </div>

      </div>
    </section>
  );
}
