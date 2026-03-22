const stats = [
  { value: "80%", label: "Cost Savings", detail: "Smart routing picks the cheapest capable model" },
  { value: "1", label: "Line Change", detail: "OpenAI-compatible — swap your base URL" },
  { value: "Auto", label: "Model Selection", detail: "Routes to the best model for each task" },
  { value: "27+", label: "Safety Levers", detail: "Governance defaults backed by research" },
  { value: "<50ms", label: "Routing Overhead", detail: "Latency you won't notice" },
  { value: "100%", label: "Cache Hits Tracked", detail: "See exactly what you save" },
];

export default function Stats() {
  return (
    <section className="border-y border-[var(--color-border)] bg-[var(--color-bg-card)]">
      <div className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-8">
          {stats.map((s) => (
            <div key={s.label} className="text-center">
              <div className="text-3xl font-extrabold text-[var(--color-accent)] tabular-nums">
                {s.value}
              </div>
              <div className="mt-1 text-sm font-semibold text-[var(--color-text)]">
                {s.label}
              </div>
              <div className="mt-0.5 text-xs text-[var(--color-text-dim)]">
                {s.detail}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
