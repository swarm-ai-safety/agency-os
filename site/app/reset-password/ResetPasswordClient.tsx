"use client";

import { FormEvent, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

type State = "idle" | "submitting" | "success" | "error";

function ResetForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState<string | null>(null);

  if (!token) {
    return (
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <p className="text-sm text-[var(--color-danger)]">
          Missing reset token. Please use the link from your email.
        </p>
        <a
          href="/forgot-password"
          className="mt-4 inline-block text-sm text-[var(--color-accent)] hover:underline"
        >
          Request a new reset link
        </a>
      </div>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setState("submitting");
    setError(null);

    try {
      const response = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setState("error");
        setError(
          payload.detail || "Reset failed. The link may have expired."
        );
        return;
      }

      setState("success");
    } catch {
      setState("error");
      setError("Network error. Please try again.");
    }
  }

  if (state === "success") {
    return (
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <p className="text-sm text-[var(--color-text)]">
          Your password has been reset.
        </p>
        <a
          href="/login"
          className="mt-4 inline-block rounded-xl bg-[var(--color-accent)] px-6 py-3 text-sm font-semibold text-black hover:brightness-110 transition-all"
        >
          Log in
        </a>
      </div>
    );
  }

  return (
    <>
      <form onSubmit={handleSubmit} className="mt-8 space-y-4">
        <label className="block">
          <span className="mb-1.5 block text-sm text-[var(--color-text-muted)]">
            New password
          </span>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-sm text-[var(--color-text)] focus:outline-none focus:border-[var(--color-accent)]"
            placeholder="At least 8 characters"
          />
        </label>

        <label className="block">
          <span className="mb-1.5 block text-sm text-[var(--color-text-muted)]">
            Confirm password
          </span>
          <input
            type="password"
            required
            minLength={8}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-sm text-[var(--color-text)] focus:outline-none focus:border-[var(--color-accent)]"
            placeholder="Re-enter your password"
          />
        </label>

        <button
          type="submit"
          disabled={state === "submitting"}
          className="w-full rounded-xl bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-black hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {state === "submitting" ? "Resetting..." : "Reset Password"}
        </button>
      </form>

      {error && (
        <p className="mt-4 text-sm text-[var(--color-danger)]">{error}</p>
      )}
    </>
  );
}

export default function ResetPasswordClient() {
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
            Set new password
          </h1>
          <p className="mt-3 text-[var(--color-text-muted)]">
            Choose a new password for your account.
          </p>
          <Suspense
            fallback={
              <p className="mt-8 text-sm text-[var(--color-text-muted)]">
                Loading...
              </p>
            }
          >
            <ResetForm />
          </Suspense>
        </section>
      </main>
    </>
  );
}
