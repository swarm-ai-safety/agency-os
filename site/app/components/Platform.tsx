const features = [
  {
    title: "One API. Every model.",
    description:
      "Drop-in replacement for OpenAI's API. Point your base URL at Agency-OS and get access to GPT-4o, Claude, Gemini, Llama, Mistral, and more — all through a single endpoint. No provider lock-in, no key juggling.",
    code: `# Switch in one line — no code changes
curl https://api.zerohumanlabs.com/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "auto",
    "messages": [{"role": "user",
      "content": "Summarize this document"}]
  }'

# "auto" picks the best model for the task`,
  },
  {
    title: "Smart routing saves you 30-80%.",
    description:
      "Not every prompt needs GPT-4o. Our router analyzes complexity and routes simple tasks to cheaper models automatically. You set the quality floor — we minimize the cost. Real-time metering shows exactly what you spend.",
    code: `# Cost optimization in action:
> Request: "What is 2+2?"
> Routed to: llama-3.1-8b (cost: $0.0001)

> Request: "Analyze this contract for risks"
> Routed to: claude-sonnet (cost: $0.012)

# Monthly savings report:
#   Before: $847.20 (all GPT-4o)
#   After:  $203.14 (smart routing)
#   Saved:  $644.06 (76%)`,
  },
  {
    title: "Governed by default. Budget-capped. Failover-ready.",
    description:
      "Hard budget ceilings prevent runaway spend. Automatic failover keeps your app running when a provider goes down. Circuit breakers freeze misbehaving requests. All safety defaults are calibrated from real simulation data — not guesswork.",
    code: `# Built-in governance:
budget_limit_usd: 500.00    # hard ceiling, enforced
failover:
  enabled: true              # auto-switch on errors
  providers: [openai, anthropic, google]
circuit_breaker:
  max_errors: 5              # freeze after 5 failures
  window_sec: 60             # within 60-second window
cache:
  enabled: true              # exact-match prompt cache
  ttl_sec: 3600              # 1-hour TTL`,
  },
];

const roadmap = [
  {
    title: "Agent Orchestration",
    description: "Deploy governed agent teams from a single YAML file. Sealed-bid task auctions, reputation scoring, and automatic demotion.",
    status: "Coming Soon",
  },
  {
    title: "Agent Wallets",
    description: "Per-agent USDC wallets on Base. Agents earn, spend, and transact — with governance rails on every transaction.",
    status: "Coming Soon",
  },
];

export default function Platform() {
  return (
    <section
      id="platform"
      className="py-24 px-6 border-t border-[var(--color-border)]"
    >
      <div className="mx-auto max-w-6xl">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            The AI gateway that pays for itself
          </h2>
          <p className="mt-4 text-[var(--color-text-muted)] max-w-2xl mx-auto">
            Route requests to the best model. Track costs in real time. Set hard
            budget limits. Fail over automatically. All through an
            OpenAI-compatible API you can adopt in one line.
          </p>
        </div>

        <div className="space-y-12">
          {features.map((f, i) => (
            <div
              key={f.title}
              className={`flex flex-col ${
                i % 2 === 1 ? "lg:flex-row-reverse" : "lg:flex-row"
              } gap-8 items-center`}
            >
              <div className="flex-1">
                <h3 className="text-xl font-bold mb-3">{f.title}</h3>
                <p className="text-[var(--color-text-muted)] leading-relaxed">
                  {f.description}
                </p>
              </div>
              <div className="flex-1 w-full">
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] overflow-hidden">
                  <div className="flex items-center gap-1.5 border-b border-[var(--color-border)] px-4 py-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
                  </div>
                  <pre className="p-5 text-sm font-mono text-[var(--color-text-muted)] overflow-x-auto leading-relaxed">
                    {f.code}
                  </pre>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Roadmap / Coming Soon */}
        <div className="mt-20">
          <h3 className="text-center text-xl font-bold mb-8 text-[var(--color-text-muted)]">
            What&apos;s next
          </h3>
          <div className="grid md:grid-cols-2 gap-6">
            {roadmap.map((item) => (
              <div
                key={item.title}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6"
              >
                <div className="flex items-center gap-3 mb-2">
                  <h4 className="text-lg font-bold">{item.title}</h4>
                  <span className="rounded-full border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10 px-2.5 py-0.5 text-xs font-semibold text-[var(--color-accent)]">
                    {item.status}
                  </span>
                </div>
                <p className="text-sm text-[var(--color-text-muted)]">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
