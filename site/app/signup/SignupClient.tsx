"use client";

import { FormEvent, useMemo, useState } from "react";

type SignupState = "idle" | "submitting" | "success" | "error";
type BillingState = "idle" | "submitting" | "error";
const DASHBOARD_API_KEY_STORAGE_KEY = "zhl_dashboard_api_key";

function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function extractErrorMessage(payload: unknown): string {
  if (!payload || typeof payload !== "object") {
    return "Signup failed. Please try again.";
  }

  const detail = (payload as { detail?: unknown }).detail;
  const direct = asText(detail);
  if (direct) return direct;

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first === "object") {
      const maybeMsg = asText((first as { msg?: unknown }).msg);
      if (maybeMsg) return maybeMsg;
    }
  }

  return "Signup failed. Please try again.";
}

export default function SignupClient() {
  const apiBase = useMemo(() => process.env.NEXT_PUBLIC_API_URL || "", []);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [tenantName, setTenantName] = useState<string>("");
  const [signupState, setSignupState] = useState<SignupState>("idle");
  const [billingState, setBillingState] = useState<BillingState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSignup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSignupState("submitting");
    setError(null);

    try {
      const response = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setSignupState("error");
        setError(extractErrorMessage(payload));
        return;
      }

      // The server-side proxy already set the session cookie.
      // api_key is returned for display; session_token is not.
      setApiKey(payload.api_key);
      setTenantName(payload.name || name);
      if (payload.api_key) {
        try {
          window.sessionStorage.setItem(
            DASHBOARD_API_KEY_STORAGE_KEY,
            payload.api_key
          );
        } catch {
          // Ignore session storage failures and keep signup flow functional.
        }
      }

      setSignupState("success");
    } catch {
      setSignupState("error");
      setError("Network error. Please try again.");
    }
  }

  async function copyKey() {
    if (!apiKey) return;
    try {
      await navigator.clipboard.writeText(apiKey);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setError("Could not copy key. Please copy it manually.");
    }
  }

  async function activatePaidPlan() {
    if (!apiKey || !email) return;
    setBillingState("submitting");
    setError(null);

    try {
      const setupResp = await fetch(`${apiBase}/api/v1/billing/setup-customer`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
        body: JSON.stringify({ email }),
      });
      const setupPayload = await setupResp.json().catch(() => ({}));
      if (!setupResp.ok) {
        setBillingState("error");
        setError(
          setupPayload.detail || "Could not initialize billing customer setup."
        );
        return;
      }

      const isHttps = window.location.protocol === "https:";
      const checkoutBody: Record<string, string> = {};
      if (isHttps) {
        checkoutBody.success_url = `${window.location.origin}/welcome?billing=active`;
        checkoutBody.cancel_url = `${window.location.origin}/welcome?billing=cancelled`;
      }

      const checkoutResp = await fetch(`${apiBase}/api/v1/billing/checkout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
        body: JSON.stringify(checkoutBody),
      });
      const checkoutPayload = await checkoutResp.json().catch(() => ({}));
      if (!checkoutResp.ok || !checkoutPayload.checkout_url) {
        setBillingState("error");
        setError(
          checkoutPayload.detail || "Could not create checkout session."
        );
        return;
      }

      window.location.href = checkoutPayload.checkout_url;
    } catch {
      setBillingState("error");
      setError("Billing setup failed. Please try again.");
    }
  }

  function openDashboard() {
    if (apiKey) {
      try {
        window.sessionStorage.setItem(DASHBOARD_API_KEY_STORAGE_KEY, apiKey);
      } catch {
        // Ignore session storage failures and keep navigation functional.
      }
    }
    window.location.href = "/dashboard";
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

      <main className="mx-auto max-w-4xl px-6 pt-32 pb-24">
        <div className="grid gap-8 md:grid-cols-[1.1fr_1fr]">
          <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8">
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
              Get your API key
            </h1>
            <p className="mt-3 text-[var(--color-text-muted)]">
              Start routing in under 2 minutes. Free tier includes smart model
              routing, cost tracking, and caching. Upgrade for higher limits
              and priority support.
            </p>

            <form onSubmit={handleSignup} className="mt-8 space-y-4">
              <label className="block">
                <span className="mb-1.5 block text-sm text-[var(--color-text-muted)]">
                  Name
                </span>
                <input
                  type="text"
                  required
                  minLength={1}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-sm text-[var(--color-text)] focus:outline-none focus:border-[var(--color-accent)]"
                  placeholder="Acme Labs"
                />
              </label>

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
                  placeholder="At least 8 characters"
                />
              </label>

              <button
                type="submit"
                disabled={signupState === "submitting"}
                className="w-full rounded-xl bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-black hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {signupState === "submitting" ? "Creating account..." : "Get API Key"}
              </button>
            </form>

            {error && (
              <p className="mt-4 text-sm text-[var(--color-danger)]">{error}</p>
            )}

            <p className="mt-6 text-center text-sm text-[var(--color-text-muted)]">
              Already have an account?{" "}
              <a
                href="/login"
                className="text-[var(--color-accent)] hover:underline"
              >
                Log in
              </a>
            </p>
          </section>

          <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8">
            {!apiKey ? (
              <>
                <h2 className="text-xl font-bold">Your API key appears here</h2>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  Submit the form to get your key. We only display it once.
                </p>
              </>
            ) : (
              <>
                <h2 className="text-xl font-bold">Welcome, {tenantName}</h2>
                <p className="mt-2 text-sm text-[var(--color-warning)]">
                  Your key is shown once. Copy it now.
                </p>
                <div className="mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                  <code className="block break-all text-sm text-[var(--color-accent)]">
                    {apiKey}
                  </code>
                  <button
                    type="button"
                    onClick={copyKey}
                    className="mt-3 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                  >
                    {copied ? "Copied" : "Copy API key"}
                  </button>
                </div>

                <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                  <h3 className="text-sm font-semibold">Next steps</h3>
                  <ul className="mt-3 space-y-2 text-sm text-[var(--color-text-muted)]">
                    <li>
                      1. Open your{" "}
                      <button
                        type="button"
                        onClick={openDashboard}
                        className="text-[var(--color-accent)] hover:underline"
                      >
                        Dashboard
                      </button>{" "}
                      without re-entering your key.
                    </li>
                    <li>
                      2. Run your first request in{" "}
                      <a
                        href="/quickstart"
                        className="text-[var(--color-accent)] hover:underline"
                      >
                        Quickstart
                      </a>
                      .
                    </li>
                    <li>
                      3. Keep{" "}
                      <a
                        href="/welcome"
                        className="text-[var(--color-accent)] hover:underline"
                      >
                        Welcome
                      </a>{" "}
                      handy for copy-ready command templates.
                    </li>
                  </ul>

                  <button
                    type="button"
                    onClick={activatePaidPlan}
                    disabled={billingState === "submitting"}
                    className="mt-4 w-full rounded-xl bg-[var(--color-accent)]/20 border border-[var(--color-accent)]/40 px-4 py-2.5 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-accent)]/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {billingState === "submitting"
                      ? "Redirecting to Stripe..."
                      : "Activate paid plan"}
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      </main>
    </>
  );
}
