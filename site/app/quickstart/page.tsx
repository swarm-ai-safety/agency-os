import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Quickstart — Zero Human Labs",
  description:
    "Go from API key to your first smart-routed LLM call in 5 minutes. Save up to 80% on AI costs with automatic model routing.",
  alternates: {
    canonical: "/quickstart",
  },
  openGraph: {
    url: "/quickstart",
  },
};

function CodeBlock({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] overflow-hidden">
      <div className="flex items-center gap-1.5 border-b border-[var(--color-border)] px-4 py-2.5">
        <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
        <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
        <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        <span className="ml-3 text-xs text-[var(--color-text-dim)] font-mono">
          {title}
        </span>
      </div>
      <div className="p-5 font-mono text-sm leading-relaxed overflow-x-auto">
        {children}
      </div>
    </div>
  );
}

function StepNumber({ n }: { n: number }) {
  return (
    <div className="flex items-center justify-center h-8 w-8 rounded-full bg-[var(--color-accent)] text-black text-sm font-bold shrink-0">
      {n}
    </div>
  );
}

function Annotation({
  field,
  children,
}: {
  field: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 py-2">
      <code className="text-[var(--color-accent)] shrink-0 text-sm">
        {field}
      </code>
      <span className="text-sm text-[var(--color-text-muted)]">{children}</span>
    </div>
  );
}

function TabGroup({
  tabs,
}: {
  tabs: { label: string; content: React.ReactNode }[];
}) {
  return (
    <div className="space-y-3">
      {tabs.map((tab) => (
        <details key={tab.label} className="group">
          <summary className="cursor-pointer text-sm font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors">
            {tab.label}
          </summary>
          <div className="mt-2">{tab.content}</div>
        </details>
      ))}
    </div>
  );
}

export default function Quickstart() {
  return (
    <>
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)]/80 backdrop-blur-xl">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <a href="/" className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
              <span className="text-sm font-bold text-black">0H</span>
            </div>
            <span className="text-lg font-bold tracking-tight">
              Zero Human Labs
            </span>
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
        {/* Header */}
        <div className="mb-16">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-1.5 text-xs text-[var(--color-text-muted)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
            5-minute guide
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight">
            Quickstart
          </h1>
          <p className="mt-4 text-lg text-[var(--color-text-muted)] max-w-2xl leading-relaxed">
            Go from API key to your first smart-routed LLM call. Drop in one
            endpoint, get automatic model selection that saves you up to 80% on
            AI costs.
          </p>
        </div>

        {/* Steps */}
        <div className="space-y-16">
          {/* Step 1: Get your API key */}
          <section>
            <div className="flex items-center gap-3 mb-4">
              <StepNumber n={1} />
              <h2 className="text-2xl font-bold">Get your API key</h2>
            </div>
            <p className="text-[var(--color-text-muted)] mb-4">
              Sign up for a free account and grab your API key in one step. No
              credit card required to start. The Free Demo is a one-time guided
              onboarding flow with one example workflow run on open-source
              models, then upgrade for continued usage.
            </p>
            <a
              href="/signup"
              className="inline-block rounded-lg bg-[var(--color-accent)] px-6 py-2.5 text-sm font-semibold text-black hover:brightness-110 transition-all"
            >
              Create Tenant
            </a>
            <p className="mt-3 text-sm text-[var(--color-text-dim)]">
              Already have a key? Skip to Step 2.
            </p>
          </section>

          {/* Step 2: Make your first call */}
          <section>
            <div className="flex items-center gap-3 mb-4">
              <StepNumber n={2} />
              <h2 className="text-2xl font-bold">Make your first call</h2>
            </div>
            <p className="text-[var(--color-text-muted)] mb-6">
              The gateway is OpenAI-compatible. Set{" "}
              <code className="text-[var(--color-accent)]">
                model: &quot;auto&quot;
              </code>{" "}
              and we&apos;ll pick the cheapest model that can handle your
              request.
            </p>

            <CodeBlock title="curl">
              <pre className="text-[var(--color-text-muted)] whitespace-pre-wrap">{`curl -X POST https://api.zero-human-labs.com/api/v1/gateway/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Translate hello to French"}
    ]
  }'`}</pre>
            </CodeBlock>

            <div className="mt-4">
              <TabGroup
                tabs={[
                  {
                    label: "Python (requests)",
                    content: (
                      <CodeBlock title="quickstart.py">
                        <pre className="text-[var(--color-text-muted)] whitespace-pre-wrap">{`import requests

response = requests.post(
    "https://api.zero-human-labs.com/api/v1/gateway/chat/completions",
    headers={
        "Content-Type": "application/json",
        "X-API-Key": "YOUR_API_KEY",
    },
    json={
        "model": "auto",
        "messages": [
            {"role": "user", "content": "Translate hello to French"}
        ],
    },
)

data = response.json()
print(data["choices"][0]["message"]["content"])
print(f"Routed to: {data.get('x_routed_model', 'N/A')}")`}</pre>
                      </CodeBlock>
                    ),
                  },
                  {
                    label: "JavaScript (fetch)",
                    content: (
                      <CodeBlock title="quickstart.js">
                        <pre className="text-[var(--color-text-muted)] whitespace-pre-wrap">{`const response = await fetch(
  "https://api.zero-human-labs.com/api/v1/gateway/chat/completions",
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": "YOUR_API_KEY",
    },
    body: JSON.stringify({
      model: "auto",
      messages: [
        { role: "user", content: "Translate hello to French" },
      ],
    }),
  }
);

const data = await response.json();
console.log(data.choices[0].message.content);
console.log("Routed to:", data.x_routed_model);`}</pre>
                      </CodeBlock>
                    ),
                  },
                ]}
              />
            </div>
          </section>

          {/* Step 3: See cost savings */}
          <section>
            <div className="flex items-center gap-3 mb-4">
              <StepNumber n={3} />
              <h2 className="text-2xl font-bold">See cost savings</h2>
            </div>
            <p className="text-[var(--color-text-muted)] mb-6">
              The response includes extra fields that show exactly what happened.
              Here&apos;s what you&apos;ll get back:
            </p>

            <CodeBlock title="response.json">
              <pre className="text-[var(--color-text-muted)] whitespace-pre-wrap">{`{
  "id": "chatcmpl-abc123...",
  "object": "chat.completion",
  "model": "gpt-4.1-nano",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Bonjour"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 3,
    "total_tokens": 15
  },
  "x_cache": "MISS",
  "x_routed_model": "gpt-4.1-nano",
  "x_routing": "auto-routed: simple -> gpt-4.1-nano"
}`}</pre>
            </CodeBlock>

            <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 space-y-1">
              <h3 className="text-sm font-bold mb-3">Response fields</h3>
              <Annotation field="x_cache">
                <strong>MISS</strong> on first request. Repeat the same query
                and it becomes <strong>HIT</strong> &mdash; served from cache at
                zero cost.
              </Annotation>
              <Annotation field="x_routed_model">
                The model that actually handled your request. You asked for{" "}
                <code>&quot;auto&quot;</code>, we picked{" "}
                <code>gpt-4.1-nano</code> because the query was simple.
              </Annotation>
              <Annotation field="x_routing">
                Why that model was chosen. Shows the complexity classification
                and routing decision.
              </Annotation>
              <Annotation field="usage.total_tokens">
                What you&apos;ll be billed for. Nano tokens cost ~80% less than
                GPT-4o tokens.
              </Annotation>
            </div>

            <div className="mt-6 rounded-xl border border-[var(--color-accent)]/20 bg-[var(--color-accent)]/5 p-6">
              <p className="text-sm text-[var(--color-text)]">
                <strong>The savings:</strong> You asked for{" "}
                <code className="text-[var(--color-accent)]">auto</code>, we
                routed to <code>gpt-4.1-nano</code> because &quot;Translate
                hello to French&quot; is a simple task. You saved ~80% vs
                sending it to GPT-4o. Same result, fraction of the cost.
              </p>
            </div>
          </section>

          {/* Step 4: Try smart routing */}
          <section>
            <div className="flex items-center gap-3 mb-4">
              <StepNumber n={4} />
              <h2 className="text-2xl font-bold">Try smart routing</h2>
            </div>
            <p className="text-[var(--color-text-muted)] mb-6">
              The router classifies each request by complexity and picks the
              cheapest adequate model. Try these three examples to see it in
              action:
            </p>

            <div className="space-y-6">
              {/* Simple */}
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <div className="flex items-center gap-2 mb-3">
                  <span className="inline-block rounded-full bg-[var(--color-success)]/10 px-3 py-0.5 text-xs font-semibold text-[var(--color-success)]">
                    Simple
                  </span>
                  <span className="text-sm text-[var(--color-text-dim)]">
                    Routes to gpt-4.1-nano
                  </span>
                </div>
                <code className="text-sm text-[var(--color-text-muted)] block">
                  &quot;Translate hello to French&quot;
                </code>
                <p className="mt-2 text-xs text-[var(--color-text-dim)]">
                  Short, single-step task. Translation, classification, simple
                  Q&amp;A all route to the cheapest model.
                </p>
              </div>

              {/* Medium */}
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <div className="flex items-center gap-2 mb-3">
                  <span className="inline-block rounded-full bg-[var(--color-warning)]/10 px-3 py-0.5 text-xs font-semibold text-[var(--color-warning)]">
                    Medium
                  </span>
                  <span className="text-sm text-[var(--color-text-dim)]">
                    Routes to gpt-4.1-mini
                  </span>
                </div>
                <code className="text-sm text-[var(--color-text-muted)] block">
                  &quot;Write a Python function to sort a list using
                  mergesort&quot;
                </code>
                <p className="mt-2 text-xs text-[var(--color-text-dim)]">
                  Multi-step generation. Code writing, structured content, and
                  moderate reasoning get a mid-tier model.
                </p>
              </div>

              {/* Complex */}
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <div className="flex items-center gap-2 mb-3">
                  <span className="inline-block rounded-full bg-[var(--color-danger)]/10 px-3 py-0.5 text-xs font-semibold text-[var(--color-danger)]">
                    Complex
                  </span>
                  <span className="text-sm text-[var(--color-text-dim)]">
                    Routes to gpt-4o / claude-sonnet-4
                  </span>
                </div>
                <code className="text-sm text-[var(--color-text-muted)] block">
                  &quot;Review this code for security vulnerabilities and
                  suggest fixes&quot;
                </code>
                <p className="mt-2 text-xs text-[var(--color-text-dim)]">
                  Deep reasoning required. Code review, architecture,
                  multi-step analysis, and long-form writing get a frontier
                  model.
                </p>
              </div>
            </div>

            <p className="mt-6 text-sm text-[var(--color-text-dim)]">
              The router uses content patterns, message length, and conversation
              depth to classify complexity. You can also override with{" "}
              <code className="text-[var(--color-accent)]">
                &quot;budget&quot;: &quot;low&quot;
              </code>{" "}
              or{" "}
              <code className="text-[var(--color-accent)]">
                &quot;budget&quot;: &quot;high&quot;
              </code>{" "}
              to force a tier.
            </p>
          </section>

          {/* Step 5: Check your usage */}
          <section>
            <div className="flex items-center gap-3 mb-4">
              <StepNumber n={5} />
              <h2 className="text-2xl font-bold">Check your usage</h2>
            </div>
            <p className="text-[var(--color-text-muted)] mb-6">
              See your requests, token counts, and costs with the stats
              endpoint:
            </p>

            <CodeBlock title="curl">
              <pre className="text-[var(--color-text-muted)] whitespace-pre-wrap">{`curl https://api.zero-human-labs.com/api/v1/gateway/stats \\
  -H "X-API-Key: YOUR_API_KEY"`}</pre>
            </CodeBlock>

            <p className="mt-4 text-sm text-[var(--color-text-muted)]">
              Returns total requests, tokens used, costs by model, and cache
              statistics. Use{" "}
              <code className="text-[var(--color-accent)]">
                /api/v1/gateway/requests
              </code>{" "}
              to see individual request logs with routing decisions.
            </p>
          </section>

          {/* Step 6: Next steps */}
          <section>
            <div className="flex items-center gap-3 mb-4">
              <StepNumber n={6} />
              <h2 className="text-2xl font-bold">Next steps</h2>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <a
                href="/#pricing"
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 hover:border-[var(--color-border-bright)] transition-all group"
              >
                <h3 className="font-bold group-hover:text-[var(--color-accent)] transition-colors">
                  Pricing
                </h3>
                <p className="mt-1 text-sm text-[var(--color-text-dim)]">
                  See per-token costs and plan tiers.
                </p>
              </a>
              <a
                href="/#platform"
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 hover:border-[var(--color-border-bright)] transition-all group"
              >
                <h3 className="font-bold group-hover:text-[var(--color-accent)] transition-colors">
                  Platform
                </h3>
                <p className="mt-1 text-sm text-[var(--color-text-dim)]">
                  Explore governance, agent teams, and orchestration.
                </p>
              </a>
              <a
                href="https://github.com/swarm-ai-safety/swarm"
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 hover:border-[var(--color-border-bright)] transition-all group"
              >
                <h3 className="font-bold group-hover:text-[var(--color-accent)] transition-colors">
                  GitHub
                </h3>
                <p className="mt-1 text-sm text-[var(--color-text-dim)]">
                  View the open-source research engine.
                </p>
              </a>
              <a
                href="/#waitlist"
                className="rounded-xl border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/5 p-5 hover:border-[var(--color-accent)]/50 transition-all group"
              >
                <h3 className="font-bold text-[var(--color-accent)]">
                  Agent Teams
                </h3>
                <p className="mt-1 text-sm text-[var(--color-text-dim)]">
                  Join the updates list for governed AI agent-team launches from YAML.
                </p>
              </a>
            </div>
          </section>
        </div>

        {/* Drop-in replacement callout */}
        <div className="mt-16 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8 text-center">
          <h3 className="text-xl font-bold mb-2">
            OpenAI-compatible. Drop-in replacement.
          </h3>
          <p className="text-[var(--color-text-muted)] max-w-xl mx-auto">
            Already using the OpenAI API? Just change the base URL and set{" "}
            <code className="text-[var(--color-accent)]">
              model: &quot;auto&quot;
            </code>
            . Your existing code works &mdash; and starts saving money
            immediately.
          </p>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--color-border)] py-12 px-6">
        <div className="mx-auto max-w-6xl flex flex-col md:flex-row items-center justify-between gap-6">
          <a href="/" className="flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-md bg-[var(--color-accent)] flex items-center justify-center">
              <span className="text-xs font-bold text-black">0H</span>
            </div>
            <span className="text-sm font-semibold">Zero Human Labs</span>
          </a>
          <div className="flex items-center gap-6 text-sm text-[var(--color-text-dim)]">
            <a
              href="/"
              className="hover:text-[var(--color-text-muted)] transition-colors"
            >
              Home
            </a>
            <a
              href="https://github.com/swarm-ai-safety/swarm"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-[var(--color-text-muted)] transition-colors"
            >
              GitHub
            </a>
            <span>&copy; {new Date().getFullYear()} Zero Human Labs</span>
          </div>
        </div>
      </footer>
    </>
  );
}
