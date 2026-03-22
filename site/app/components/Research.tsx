const findings = [
  {
    title: "Circuit breakers prevent cascading failures",
    metric: "+81% welfare, -11% toxicity",
    effect: "d = 1.64",
    confidence: "Proven",
    detail:
      "When an agent goes off the rails, the system freezes it automatically. This alone outperforms every other safety mechanism we tested.",
  },
  {
    title: "Complex agents underperform simple ones",
    metric: "2.3-2.8x less earnings",
    effect: "Depth-5 RLM",
    confidence: "Proven",
    detail:
      "Agents with deeper strategic reasoning consistently earn less than straightforward ones. Our defaults favor simplicity for a reason.",
  },
  {
    title: "Collusion detection catches bad actors",
    metric: "137x wealth gap under monitoring",
    effect: "d = 3.51",
    confidence: "Proven",
    detail:
      "When agents try to collude, behavioral monitoring makes it economically devastating for them. Built into every org.",
  },
  {
    title: "Sybil attacks still work everywhere",
    metric: "100% success rate",
    effect: "All configs",
    confidence: "Open",
    detail:
      "Fake identities beat every governance config we tested. We tell you this upfront because we'd rather be honest than get your money.",
  },
  {
    title: "Tax your agents too much and they stop working",
    metric: "Phase transition at 5%",
    effect: "S-curve",
    confidence: "Proven",
    detail:
      "Transaction taxes above 5% cause a sharp welfare collapse. That's why our balanced preset caps at exactly 5%.",
  },
  {
    title: "Diverse teams outperform uniform ones",
    metric: "20% honest > 100% honest",
    effect: "66 runs",
    confidence: "Proven",
    detail:
      "Mixed agent populations with different strategies outperform homogeneous ones. Our packages include agent diversity by design.",
  },
];

const confidenceColor: Record<string, string> = {
  Proven: "text-[var(--color-success)]",
  Open: "text-[var(--color-danger)]",
};

export default function Research() {
  return (
    <section id="proof" className="py-24 px-6">
      <div className="mx-auto max-w-6xl">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Why these defaults and not others
          </h2>
          <p className="mt-4 text-[var(--color-text-muted)] max-w-2xl mx-auto">
            We ran 146 simulations with 43 agent types across 27 governance
            configurations. Here&apos;s what we found &mdash; including what
            doesn&apos;t work yet.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {findings.map((f) => (
            <div
              key={f.title}
              className="group rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 hover:border-[var(--color-border-bright)] hover:bg-[var(--color-bg-card-hover)] transition-all"
            >
              <div className="flex items-center gap-2 mb-3">
                <span
                  className={`text-xs font-mono font-semibold ${confidenceColor[f.confidence]}`}
                >
                  {f.confidence}
                </span>
                <span className="text-xs text-[var(--color-text-dim)] font-mono">
                  {f.effect}
                </span>
              </div>
              <h3 className="text-base font-semibold leading-snug mb-2">
                {f.title}
              </h3>
              <div className="text-sm font-mono text-[var(--color-accent)] mb-3">
                {f.metric}
              </div>
              <p className="text-sm text-[var(--color-text-dim)] leading-relaxed">
                {f.detail}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-10 text-center">
          <a
            href="https://swarm-ai.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-[var(--color-accent)] hover:underline"
          >
            All 84 claims with evidence chains at swarm-ai.org &rarr;
          </a>
        </div>
      </div>
    </section>
  );
}
