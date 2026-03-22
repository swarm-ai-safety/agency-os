const columns = [
  "Agency-OS",
  "LangGraph / CrewAI / Autogen",
  "Single-agent tools",
  "Low-code builders",
];

const rows = [
  {
    category: "Who it's for",
    values: [
      "Solo founders and small teams who want autonomy without babysitting",
      "Developer teams willing to write orchestration code",
      "Individual users running one task at a time",
      "Non-technical teams building visual workflows",
    ],
  },
  {
    category: "Task allocation",
    values: [
      "Sealed-bid auction — best agent wins every task automatically",
      "Fixed graphs, rule-based routing, or manual handoffs",
      "No internal competition or routing",
      "Drag-and-drop sequential flows",
    ],
  },
  {
    category: "Cost governance",
    values: [
      "Per-agent wallets, org-level hard ceilings, spend stops at the limit",
      "External tracking or no budget enforcement",
      "Per-user awareness only",
      "Platform subscription, no agent-level budgeting",
    ],
  },
  {
    category: "Runaway protection",
    values: [
      "Circuit breakers freeze agents after N violations (+81% welfare, CB-001)",
      "Manual intervention or retry-based",
      "Prompt-level retry loops",
      "Timeout-based, no behavioral analysis",
    ],
  },
  {
    category: "Agent quality",
    values: [
      "Reputation scores demote low performers, promote specialists automatically",
      "No built-in reputation or demotion",
      "Single agent — no competition baseline",
      "No performance-based routing",
    ],
  },
  {
    category: "Setup complexity",
    values: [
      "One YAML file — no orchestration code, no visual builder",
      "Requires developer assembly and graph construction",
      "Simple but limited to one agent",
      "Visual builder with limited governance controls",
    ],
  },
];

export default function CompetitiveComparison() {
  return (
    <section className="px-6 py-24 border-t border-[var(--color-border)]">
      <div className="mx-auto max-w-6xl">
        <div className="mb-12 text-center">
          <p className="text-xs uppercase tracking-[0.16em] text-[var(--color-accent)]">
            Why us vs alternatives
          </p>
          <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold tracking-tight">
            Governance-first, not orchestration-first
          </h2>
          <p className="mt-4 mx-auto max-w-3xl text-[var(--color-text-muted)]">
            Other frameworks make you build the safety layer. Agency-OS ships it
            as the foundation &mdash; calibrated from simulation research, not
            defaults picked from a blog post.
          </p>
        </div>

        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)]">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg)]/60">
                <th className="p-4 text-left text-xs uppercase tracking-wide text-[var(--color-text-dim)]">
                  Capability
                </th>
                {columns.map((col) => (
                  <th
                    key={col}
                    className="p-4 text-left text-xs uppercase tracking-wide text-[var(--color-text-dim)]"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr
                  key={row.category}
                  className={
                    idx < rows.length - 1
                      ? "border-b border-[var(--color-border)]"
                      : undefined
                  }
                >
                  <td className="p-4 align-top text-sm font-semibold text-[var(--color-text)]">
                    {row.category}
                  </td>
                  {row.values.map((value, valueIdx) => (
                    <td
                      key={`${row.category}-${valueIdx}`}
                      className={`p-4 align-top text-sm ${
                        valueIdx === 0
                          ? "text-[var(--color-text)]"
                          : "text-[var(--color-text-muted)]"
                      }`}
                    >
                      {value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
