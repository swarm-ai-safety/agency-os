"use client";

import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Keep the original stack visible in production browser consoles.
    // eslint-disable-next-line no-console
    console.error("Dashboard route error:", error);
  }, [error]);

  return (
    <main className="min-h-screen bg-[var(--color-bg)] px-6 py-12 text-[var(--color-text)]">
      <div className="mx-auto max-w-2xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8">
        <h1 className="text-2xl font-bold">Dashboard failed to load</h1>
        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
          A client-side error interrupted rendering. Retry once, then share the first
          browser console error line so we can patch the exact failing path.
        </p>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={reset}
            className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-black"
          >
            Retry
          </button>
          <a
            href="/"
            className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold"
          >
            Back to Home
          </a>
        </div>
      </div>
    </main>
  );
}
