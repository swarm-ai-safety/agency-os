"use client";

import { FormEvent, useState } from "react";

type State = "idle" | "submitting" | "sent" | "error";

export default function ForgotPasswordClient() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("submitting");
    setError(null);

    try {
      const response = await fetch("/api/auth/request-reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setState("error");
        setError(payload.detail || "Something went wrong. Please try again.");
        return;
      }

      setState("sent");
    } catch {
      setState("error");
      setError("Network error. Please try again.");
    }
  }

  return (
    <>
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)]/80 backdrop-blur-xl">
        <div className="mx-auto max-w-4xl flex items-center justify-between px-6 py-4">
          <a href="/" className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
              <span className="text-sm font-bold text-black">0H</span>
            </div>
            <span className="text-lg font-bold tracking-tight">
              Zero Human Labs
            </span>
          </a>
          <a
            href="/login"
            className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            Back to login
          </a>
        </div>
      </nav>

      <main className="mx-auto max-w-md px-6 pt-32 pb-24">
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8">
          <h1 className="text-3xl font-extrabold tracking-tight">
            Reset password
          </h1>
          <p className="mt-3 text-[var(--color-text-muted)]">
            Enter your email and we&apos;ll send you a link to reset your
            password.
          </p>

          {state === "sent" ? (
            <div className="mt-8 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
              <p className="text-sm text-[var(--color-text)]">
                If that email is registered, you&apos;ll receive a reset link
                shortly. Check your inbox and spam folder.
              </p>
              <a
                href="/login"
                className="mt-4 inline-block text-sm text-[var(--color-accent)] hover:underline"
              >
                Back to login
              </a>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-8 space-y-4">
              <label className="block">
                <span className="mb-1.5 block text-sm text-[var(--color-text-muted)]">
                  Email
                </span>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-sm text-[var(--color-text)] focus:outline-none focus:border-[var(--color-accent)]"
                  placeholder="you@company.com"
                />
              </label>

              <button
                type="submit"
                disabled={state === "submitting"}
                className="w-full rounded-xl bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-black hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {state === "submitting" ? "Sending..." : "Send Reset Link"}
              </button>
            </form>
          )}

          {error && (
            <p className="mt-4 text-sm text-[var(--color-danger)]">{error}</p>
          )}

          <p className="mt-6 text-center text-sm text-[var(--color-text-muted)]">
            Remember your password?{" "}
            <a
              href="/login"
              className="text-[var(--color-accent)] hover:underline"
            >
              Log in
            </a>
          </p>
        </section>
      </main>
    </>
  );
}
