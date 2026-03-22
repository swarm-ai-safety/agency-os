const claims = [
  {
    id: "CB-001",
    claim: "Circuit breakers dominate all governance configurations",
    runs: 70,
    effect: "d = 1.64",
    status: "replicated",
  },
  {
    id: "TX-001",
    claim: "Transaction tax > 5% reduces ecosystem welfare",
    runs: 29,
    effect: "d = 1.18",
    status: "replicated",
  },
  {
    id: "CL-001",
    claim: "Behavioral monitoring creates 137x wealth gap for colluders",
    runs: 13,
    effect: "d = 3.51",
    status: "replicated",
  },
  {
    id: "AG-001",
    claim: "Depth-5 RLM agents earn 2.3-2.8x less than honest agents",
    runs: 33,
    effect: "d > 1.0",
    status: "replicated",
  },
  {
    id: "SY-001",
    claim: "Sybil attacks succeed against all governance configurations",
    runs: 13,
    effect: "100%",
    status: "open problem",
  },
  {
    id: "HT-001",
    claim: "20% honest agents outperform homogeneous populations",
    runs: 66,
    effect: "heterogeneous > homo",
    status: "replicated",
  },
];

const statusStyle: Record<string, string> = {
  replicated:
    "border-[var(--color-success)]/30 bg-[var(--color-success)]/10 text-[var(--color-success)]",
  "open problem":
    "border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 text-[var(--color-danger)]",
};

export default function Claims() {
  return (
    <section
      id="claims"
      className="py-24 px-6 border-t border-[var(--color-border)] bg-[var(--color-bg-card)]"
    >
      <div className="mx-auto max-w-5xl">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            We show our work
          </h2>
          <p className="mt-4 text-[var(--color-text-muted)] max-w-2xl mx-auto">
            Every claim is reproducible. Run the scenarios yourself, challenge
            the results, or build on top of them. That&apos;s the point.
          </p>
        </div>

        <div className="rounded-xl border border-[var(--color-border)] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg)]">
                <th className="text-left px-5 py-3 font-mono text-xs text-[var(--color-text-dim)]">
                  ID
                </th>
                <th className="text-left px-5 py-3 font-mono text-xs text-[var(--color-text-dim)]">
                  Claim
                </th>
                <th className="text-left px-5 py-3 font-mono text-xs text-[var(--color-text-dim)] hidden md:table-cell">
                  Runs
                </th>
                <th className="text-left px-5 py-3 font-mono text-xs text-[var(--color-text-dim)] hidden md:table-cell">
                  Effect
                </th>
                <th className="text-left px-5 py-3 font-mono text-xs text-[var(--color-text-dim)]">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {claims.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-bg-card-hover)] transition-colors"
                >
                  <td className="px-5 py-3.5 font-mono text-[var(--color-accent)] text-xs">
                    {c.id}
                  </td>
                  <td className="px-5 py-3.5 text-[var(--color-text)]">
                    {c.claim}
                  </td>
                  <td className="px-5 py-3.5 font-mono text-[var(--color-text-muted)] hidden md:table-cell">
                    {c.runs}
                  </td>
                  <td className="px-5 py-3.5 font-mono text-[var(--color-text-muted)] hidden md:table-cell">
                    {c.effect}
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${statusStyle[c.status]}`}
                    >
                      {c.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-6 text-center text-sm text-[var(--color-text-dim)]">
          <a
            href="https://github.com/swarm-ai-safety/swarm"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-accent)] hover:underline"
          >
            pip install swarm-safety
          </a>
          {" "}&mdash; reproduce any claim in under 60 seconds
        </div>
      </div>
    </section>
  );
}
