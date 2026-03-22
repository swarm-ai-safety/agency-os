"use client";

import { useSearchParams } from "next/navigation";

export default function WelcomeClient() {
  const params = useSearchParams();
  const billingState = params?.get("billing");
  const billingActive = billingState === "active";

  return (
    <>
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)]/80 backdrop-blur-xl">
        <div className="mx-auto max-w-4xl flex items-center justify-between px-6 py-4">
          <a href="/" className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
              <span className="text-sm font-bold text-black">0H</span>
            </div>
            <span className="text-lg font-bold tracking-tight">Zero Human Labs</span>
          </a>
          <a
            href="/signup"
            className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-black hover:brightness-110 transition-all"
          >
            Sign Up
          </a>
        </div>
      </nav>

      <main className="mx-auto max-w-3xl px-6 pt-32 pb-24">
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8">
          <h1 className="text-4xl font-extrabold tracking-tight">Welcome</h1>
          <p className="mt-3 text-[var(--color-text-muted)]">
            You&apos;re ready to make your first request. Plug in your API key and
            run this command.
          </p>
          {billingActive && (
            <div className="mt-4 inline-flex items-center rounded-full border border-[var(--color-success)]/30 bg-[var(--color-success)]/10 px-3 py-1 text-xs font-semibold text-[var(--color-success)]">
              Billing active
            </div>
          )}
        </div>

        <section className="mt-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
          <h2 className="text-xl font-bold">Quickstart curl</h2>
          <pre className="mt-4 overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 text-sm text-[var(--color-text-muted)]">{`curl -X POST https://api.zero-human-labs.com/api/v1/gateway/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -d '{
    "model": "auto",
    "messages": [
      {"role":"user","content":"Summarize this API in one sentence"}
    ]
  }'`}</pre>
          <p className="mt-3 text-xs text-[var(--color-text-dim)]">
            Replace <code>YOUR_API_KEY</code> with the key shown on signup.
          </p>
        </section>

        <section className="mt-6">
          <a
            href="/quickstart"
            className="block rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4 hover:border-[var(--color-border-bright)]"
          >
            <h3 className="text-sm font-semibold">Quickstart</h3>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              End-to-end examples in curl, Python, and JS.
            </p>
          </a>
        </section>
      </main>
    </>
  );
}
