export default function Problem() {
  return (
    <section id="problem" className="py-24 px-6">
      <div className="mx-auto max-w-6xl">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            AI API costs are unpredictable. Your gateway should fix that.
          </h2>
          <p className="mt-4 text-[var(--color-text-muted)] max-w-2xl mx-auto">
            You&apos;re juggling multiple providers, managing API keys everywhere,
            and watching costs spike without warning. One missed rate limit or
            wrong model choice blows your budget. You need smart routing with
            hard cost controls &mdash; not another dashboard to watch.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8">
            <h3 className="text-lg font-bold text-[var(--color-text-dim)] mb-4">
              Direct API calls / basic proxies
            </h3>
            <ul className="space-y-3 text-sm text-[var(--color-text-muted)]">
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-text-dim)] mt-0.5 shrink-0">&times;</span>
                No cost visibility until the invoice arrives
              </li>
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-text-dim)] mt-0.5 shrink-0">&times;</span>
                Locked to one provider &mdash; no automatic failover
              </li>
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-text-dim)] mt-0.5 shrink-0">&times;</span>
                Manual model selection leaves savings on the table
              </li>
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-text-dim)] mt-0.5 shrink-0">&times;</span>
                No caching &mdash; identical prompts cost you every time
              </li>
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-text-dim)] mt-0.5 shrink-0">&times;</span>
                No budget guardrails &mdash; one bad loop drains your credits
              </li>
            </ul>
          </div>

          <div className="rounded-xl border border-[var(--color-accent)]/20 bg-[var(--color-accent)]/5 p-8">
            <h3 className="text-lg font-bold text-[var(--color-accent)] mb-4">
              Building with Agency-OS Gateway
            </h3>
            <ul className="space-y-3 text-sm text-[var(--color-text-muted)]">
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-accent)] mt-0.5 shrink-0">&#10003;</span>
                Real-time cost tracking per request, per model, per tenant
              </li>
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-accent)] mt-0.5 shrink-0">&#10003;</span>
                Automatic failover across providers &mdash; zero downtime
              </li>
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-accent)] mt-0.5 shrink-0">&#10003;</span>
                Smart routing picks the cheapest model that meets your quality bar
              </li>
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-accent)] mt-0.5 shrink-0">&#10003;</span>
                Built-in caching saves up to 80% on repeated prompts
              </li>
              <li className="flex items-start gap-3">
                <span className="text-[var(--color-accent)] mt-0.5 shrink-0">&#10003;</span>
                Hard budget ceilings &mdash; spend stops at the limit you set
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
