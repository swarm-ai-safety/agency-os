"use client";

import { useState, type FormEvent } from "react";

export default function Waitlist() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<
    "idle" | "submitting" | "success" | "rate_limited" | "error"
  >("idle");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("submitting");

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
      const res = await fetch(`${apiBase}/api/v1/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      if (res.ok) {
        setStatus("success");
        setEmail("");
        if (typeof window !== "undefined" && (window as any).plausible) {
          (window as any).plausible("Waitlist Signup");
        }
      } else if (res.status === 429) {
        setStatus("rate_limited");
      } else {
        setStatus("error");
      }
    } catch {
      setStatus("error");
    }
  }

  return (
    <section
      id="waitlist"
      className="py-24 px-6 border-t border-[var(--color-border)] bg-[var(--color-bg-card)]"
    >
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
          Stay ahead of new capabilities
        </h2>
        <p className="mt-4 text-[var(--color-text-muted)] max-w-xl mx-auto leading-relaxed">
          API signup is live today. Join the updates list for major launches,
          advanced agent-team features, and practical playbooks from real
          operator teams.
        </p>

        {status === "success" ? (
          <div
            aria-live="polite"
            className="mt-10 rounded-xl border border-[var(--color-success)]/30 bg-[var(--color-success)]/10 px-6 py-4 text-sm text-[var(--color-success)]"
          >
            <p className="font-semibold">Thanks, you&apos;re on the updates list.</p>
            <p className="mt-1 text-[var(--color-text)]">
              We&apos;ll email product updates and release announcements.
            </p>
          </div>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="mt-10 flex flex-col sm:flex-row gap-3 max-w-md mx-auto"
          >
            <input
              type="email"
              placeholder="you@startup.com"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="flex-1 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3.5 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-accent)] transition-colors"
            />
            <button
              type="submit"
              disabled={status === "submitting"}
              className="rounded-xl bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-black hover:brightness-110 transition-all whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {status === "submitting" ? "Submitting..." : "Get Product Updates"}
            </button>
          </form>
        )}

        {status === "rate_limited" && (
          <p aria-live="polite" className="mt-3 text-xs text-[var(--color-danger)]">
            Too many attempts from this network. Please try again later.
          </p>
        )}

        {status === "error" && (
          <p className="mt-3 text-xs text-[var(--color-danger)]">
            Something went wrong. Please try again.
          </p>
        )}

        <p className="mt-4 text-xs text-[var(--color-text-dim)]">
          API access is live now. No credit card required to start.
        </p>
      </div>
    </section>
  );
}
