export default function DifferentiationCallout() {
  return (
    <section className="px-6 py-10">
      <div className="mx-auto max-w-6xl rounded-xl border border-[var(--color-accent)]/25 bg-[var(--color-accent)]/10 p-6 sm:p-8">
        <p className="text-xs uppercase tracking-[0.16em] text-[var(--color-accent)]">
          Why teams switch
        </p>
        <h2 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight">
          Smart routing with governance built in
        </h2>
        <p className="mt-3 max-w-3xl text-[var(--color-text-muted)]">
          Every request is routed to the best model for the job &mdash; balancing cost,
          latency, and capability automatically. Built-in governance prevents runaway
          spend and enforces safety defaults calibrated from real simulation data.
        </p>
      </div>
    </section>
  );
}
