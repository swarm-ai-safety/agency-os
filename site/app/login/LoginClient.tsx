"use client";

import { FormEvent, useState } from "react";

type LoginState = "idle" | "submitting" | "error";

export default function LoginClient() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<LoginState>("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("submitting");
    setError(null);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier: email, password }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setState("error");
        setError(payload.detail || "Invalid credentials. Please try again.");
        return;
      }

      window.location.href = "/dashboard";
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
            <span className="text-lg font-bold tracking-tight">Zero Human Labs</span>
          </a>
          <a
            href="/quickstart"
            className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            Quickstart
          </a>
        </div>
      </nav>

      <main className="mx-auto max-w-md px-6 pt-32 pb-24">
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8">
          <h1 className="text-3xl font-extrabold tracking-tight">Log in</h1>
          <p className="mt-3 text-[var(--color-text-muted)]">
            Sign in to access your dashboard and API.
          </p>

          <form onSubmit={handleLogin} className="mt-8 space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-sm text-[var(--color-text-muted)]">
                Email
              </span>
              <input
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-sm text-[var(--color-text)] focus:outline-none focus:border-[var(--color-accent)]"
                placeholder="you@company.com"
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-sm text-[var(--color-text-muted)]">
                Password
              </span>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-sm text-[var(--color-text)] focus:outline-none focus:border-[var(--color-accent)]"
                placeholder="Your password"
              />
            </label>

            <div className="flex items-center justify-between">
              <a
                href="/forgot-password"
                className="text-sm text-[var(--color-accent)] hover:underline"
              >
                Forgot password?
              </a>
            </div>

            <button
              type="submit"
              disabled={state === "submitting"}
              className="w-full rounded-xl bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-black hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {state === "submitting" ? "Logging in..." : "Log In"}
            </button>
          </form>

          {error && (
            <p className="mt-4 text-sm text-[var(--color-danger)]">{error}</p>
          )}

          <p className="mt-6 text-center text-sm text-[var(--color-text-muted)]">
            Don&apos;t have an account?{" "}
            <a
              href="/signup"
              className="text-[var(--color-accent)] hover:underline"
            >
              Sign up
            </a>
          </p>
        </section>
      </main>
    </>
  );
}
