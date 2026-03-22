"use client";

import { useState } from "react";
import {
  calcAgencyOsCost,
  calcDirectCost,
  calcSmartRoutingCost,
  fmt,
  fmtDollars,
  models,
} from "./pricing-utils";

/* ── Plan tiers ─────────────────────────────────────────────── */

const tiers = [
  {
    name: "Free Demo",
    price: "$0",
    period: "one-time",
    description:
      "Free Demo — $0 one-time onboarding: we set up the basics and run one example workflow on open-source models. Upgrade required for continued usage.",
    highlight: false,
    cta: "Start Free Demo",
    href: "/signup",
    features: [
      "1 agent",
      "Guided setup included",
      "1 example workflow run",
      "Open-source model pool for demo run",
      "Smart routing (model=\"auto\")",
      "Balanced governance preset",
      "Real-time metering",
      "Community support",
    ],
    limits: [
      "No recurring monthly token bucket",
      "Upgrade required after demo run",
      "No failover or eval harness",
      "Single governance preset",
    ],
  },
  {
    name: "Pro",
    price: "$49",
    period: "/mo + usage",
    description: "For teams running production agent workflows.",
    highlight: true,
    cta: "Upgrade to Pro",
    href: "/signup",
    features: [
      "Unlimited agents",
      "1M tokens/month included",
      "All governance presets (conservative, balanced, aggressive)",
      "Cross-provider failover",
      "Eval harness (5 dimensions: toxicity, relevance, quality, hallucination, factuality)",
      "Trust score monitoring",
      "Per-agent budget caps",
      "Priority support",
      "10% volume discount on overages",
    ],
    limits: [],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "Dedicated infrastructure and compliance controls.",
    highlight: false,
    cta: "Contact Sales",
    href: "/signup",
    features: [
      "Everything in Pro",
      "Custom governance profiles",
      "Dedicated tenant isolation",
      "SLA guarantees",
      "SSO / SAML",
      "Audit log export",
      "Volume pricing (negotiated)",
      "Dedicated support channel",
    ],
    limits: [],
  },
];

/* ── FAQ ────────────────────────────────────────────────────── */

const faqs = [
  {
    q: "How does smart routing save money?",
    a: "When you send model=\"auto\", our router classifies your request by complexity and routes it to the cheapest adequate model. Simple tasks go to GPT-4.1 Nano or Mini instead of Opus. Most workloads are 60%+ simple requests, cutting costs 30-80%.",
  },
  {
    q: "Is it OpenAI-compatible?",
    a: "Yes. Point your existing OpenAI SDK at our gateway endpoint. Same request/response format, same streaming support. It's a drop-in replacement.",
  },
  {
    q: "What happens after the free demo run?",
    a: "After your one example workflow run, token-consuming requests return a payment required response until you upgrade to Pro.",
  },
  {
    q: "Can I use my own API keys?",
    a: "Yes, on Enterprise custom plans. Default plans use Agency-OS managed billing so teams get predictable monthly spend, smart routing, failover, and unified metering.",
  },
  {
    q: "How is usage metered?",
    a: "Per-token, in real-time. Every request logs input and output tokens with per-agent attribution. View usage in the dashboard or query the metering API.",
  },
  {
    q: "Do I pay per agent?",
    a: "No. You pay for token consumption. Run as many agents as your plan allows with no per-agent fees.",
  },
];

/* ── Slider steps (log scale feel) ───────────────────────────── */

const sliderSteps = [
  100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000,
  10_000_000, 25_000_000, 50_000_000, 100_000_000,
];

/* ── Component ──────────────────────────────────────────────── */

export default function Pricing() {
  const [showModels, setShowModels] = useState(false);
  const [sliderIdx, setSliderIdx] = useState(3); // 1M default
  const [selectedModel, setSelectedModel] = useState("Claude Sonnet 4");
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const tokens = sliderSteps[sliderIdx];
  const direct = calcDirectCost(selectedModel, tokens);
  const agencyOs = calcAgencyOsCost(selectedModel, tokens);
  const savings = direct - agencyOs;
  const savingsPct = direct > 0 ? (savings / direct) * 100 : 0;

  return (
    <section
      id="pricing"
      className="py-24 px-6 border-t border-[var(--color-border)]"
    >
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Save 30-80% on AI API calls
          </h2>
          <p className="mt-4 text-[var(--color-text-muted)] max-w-2xl mx-auto">
            Managed model access with one-time guided demo onboarding, then tiered
            monthly plans for continued usage. Enterprise BYOK is available on
            custom plans.
          </p>
        </div>

        {/* ── Plan cards ───────────────────────────────────────── */}
        <div className="grid md:grid-cols-3 gap-6 mb-20">
          {tiers.map((t) => (
            <div
              key={t.name}
              className={`rounded-xl border p-8 flex flex-col ${
                t.highlight
                  ? "border-[var(--color-accent)]/40 bg-[var(--color-accent)]/5 ring-1 ring-[var(--color-accent)]/20"
                  : "border-[var(--color-border)] bg-[var(--color-bg-card)]"
              }`}
            >
              <div className="mb-6">
                <h3 className="text-lg font-bold">{t.name}</h3>
                <div className="mt-2 flex items-baseline gap-1.5">
                  <span className="text-3xl font-extrabold">{t.price}</span>
                  {t.period && (
                    <span className="text-sm text-[var(--color-text-dim)]">
                      {t.period}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  {t.description}
                </p>
              </div>

              <ul className="space-y-2.5 mb-4 flex-1">
                {t.features.map((f) => (
                  <li
                    key={f}
                    className="flex items-start gap-2.5 text-sm text-[var(--color-text-muted)]"
                  >
                    <span className="text-[var(--color-accent)] mt-0.5 shrink-0">
                      &#10003;
                    </span>
                    {f}
                  </li>
                ))}
                {t.limits.map((l) => (
                  <li
                    key={l}
                    className="flex items-start gap-2.5 text-sm text-[var(--color-text-dim)]"
                  >
                    <span className="text-[var(--color-text-dim)] mt-0.5 shrink-0">
                      &mdash;
                    </span>
                    {l}
                  </li>
                ))}
              </ul>

              <a
                href={t.href}
                className={`block text-center rounded-lg px-4 py-2.5 text-sm font-semibold transition-all ${
                  t.highlight
                    ? "bg-[var(--color-accent)] text-black hover:brightness-110"
                    : "border border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-border-bright)] hover:text-[var(--color-text)]"
                }`}
              >
                {t.cta}
              </a>
            </div>
          ))}
        </div>

        {/* ── Cost savings calculator ──────────────────────────── */}
        <div className="mx-auto max-w-3xl mb-20">
          <h3 className="text-center text-2xl font-bold mb-2">
            Cost savings calculator
          </h3>
          <p className="text-center text-sm text-[var(--color-text-muted)] mb-8">
            See how much smart routing saves compared to calling the API directly.
          </p>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8">
            {/* Controls */}
            <div className="grid sm:grid-cols-2 gap-6 mb-8">
              <div>
                <label className="block text-xs text-[var(--color-text-dim)] mb-2">
                  Monthly token volume
                </label>
                <input
                  type="range"
                  min={0}
                  max={sliderSteps.length - 1}
                  value={sliderIdx}
                  onChange={(e) => setSliderIdx(Number(e.target.value))}
                  className="w-full accent-[var(--color-accent)]"
                />
                <div className="text-right text-sm font-mono mt-1">
                  {fmt(tokens)} tokens
                </div>
              </div>
              <div>
                <label className="block text-xs text-[var(--color-text-dim)] mb-2">
                  Primary model
                </label>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text)]"
                >
                  {models.map((m) => (
                    <option key={m.name} value={m.name}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Results */}
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="rounded-lg bg-[var(--color-bg)] p-4">
                <div className="text-xs text-[var(--color-text-dim)] mb-1">
                  Direct API cost
                </div>
                <div className="text-xl font-bold font-mono">
                  {fmtDollars(direct)}
                </div>
              </div>
              <div className="rounded-lg bg-[var(--color-bg)] p-4">
                <div className="text-xs text-[var(--color-text-dim)] mb-1">
                  Agency-OS cost
                </div>
                <div className="text-xl font-bold font-mono text-[var(--color-accent)]">
                  {fmtDollars(agencyOs)}
                </div>
              </div>
              <div className="rounded-lg bg-[var(--color-bg)] p-4">
                <div className="text-xs text-[var(--color-text-dim)] mb-1">
                  You save
                </div>
                <div className="text-xl font-bold font-mono text-green-400">
                  {savings > 0 ? fmtDollars(savings) : "$0.00"}
                </div>
                {savingsPct > 0 && (
                  <div className="text-xs text-green-400 mt-0.5">
                    {savingsPct.toFixed(0)}% less
                  </div>
                )}
              </div>
            </div>

            <p className="mt-4 text-center text-xs text-[var(--color-text-dim)]">
              Assumes 60% simple / 30% medium / 10% complex request mix with
              smart routing. Plus you get: failover, caching, governance, audit
              trail &mdash; included.
            </p>
          </div>
        </div>

        {/* ── Model pricing table ──────────────────────────────── */}
        <div className="mx-auto max-w-3xl mb-20">
          <button
            onClick={() => setShowModels(!showModels)}
            className="w-full flex items-center justify-between text-left rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] px-6 py-4 hover:border-[var(--color-border-bright)] transition-colors"
          >
            <span className="font-bold">Model pricing</span>
            <span className="text-[var(--color-text-dim)] text-sm">
              {showModels ? "Hide" : "Show"} per-model rates
              <span className="ml-2 inline-block transition-transform" style={{ transform: showModels ? "rotate(180deg)" : "rotate(0deg)" }}>
                &#9660;
              </span>
            </span>
          </button>

          {showModels && (
            <div className="mt-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg)]">
                    <th className="text-left px-5 py-3 text-xs text-[var(--color-text-dim)]">
                      Model
                    </th>
                    <th className="text-right px-5 py-3 text-xs text-[var(--color-text-dim)]">
                      Input / 1M tokens
                    </th>
                    <th className="text-right px-5 py-3 text-xs text-[var(--color-text-dim)]">
                      Output / 1M tokens
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <tr
                      key={m.name}
                      className="border-b border-[var(--color-border)] last:border-0"
                    >
                      <td className="px-5 py-3 text-[var(--color-text)]">
                        <span>{m.name}</span>
                        <span className="ml-2 text-xs text-[var(--color-text-dim)]">
                          {m.provider}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-[var(--color-text-muted)]">
                        {fmtDollars(m.input)}
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-[var(--color-text-muted)]">
                        {fmtDollars(m.output)}
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-[var(--color-bg)]">
                    <td className="px-5 py-3 text-[var(--color-accent)] font-medium">
                      Auto (smart routing)
                    </td>
                    <td
                      colSpan={2}
                      className="px-5 py-3 text-right text-xs text-[var(--color-text-dim)]"
                    >
                      Varies &mdash; system picks cheapest adequate model
                    </td>
                  </tr>
                </tbody>
              </table>
              <p className="px-5 py-3 text-xs text-[var(--color-text-dim)] border-t border-[var(--color-border)]">
                Prices include 30% platform margin covering routing, failover,
                caching, governance, metering, and eval infrastructure.
              </p>
            </div>
          )}
        </div>

        {/* ── FAQ ──────────────────────────────────────────────── */}
        <div className="mx-auto max-w-3xl">
          <h3 className="text-center text-2xl font-bold mb-8">
            Frequently asked questions
          </h3>
          <div className="space-y-2">
            {faqs.map((faq, i) => (
              <div
                key={i}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] overflow-hidden"
              >
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between text-left px-6 py-4 hover:bg-[var(--color-bg)] transition-colors"
                >
                  <span className="font-medium text-sm">{faq.q}</span>
                  <span
                    className="text-[var(--color-text-dim)] text-sm ml-4 shrink-0 transition-transform"
                    style={{ transform: openFaq === i ? "rotate(180deg)" : "rotate(0deg)" }}
                  >
                    &#9660;
                  </span>
                </button>
                {openFaq === i && (
                  <div className="px-6 pb-4 text-sm text-[var(--color-text-muted)]">
                    {faq.a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
