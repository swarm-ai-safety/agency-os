"use client";

import { useState, useRef } from "react";

const templates = [
  {
    name: "Biotech Research Team",
    slug: "biotech_research",
    featured: true,
    description:
      "Multi-agent research swarm for literature review, evidence synthesis, and critical analysis. Based on our Hermes Agent immunotherapy demo.",
    agents: [
      "Literature Reviewer x2",
      "Synthesis Analyst",
      "Critical Reviewer",
      "Domain Specialist",
      "Research Coordinator",
    ],
    governance: "Conservative",
    budget: "$60",
    workflow: "Search > Analyze > Synthesize > Critique > Report",
    useCases: [
      "Systematic literature reviews",
      "Drug target analysis",
      "Clinical trial landscape mapping",
      "Regulatory evidence gathering",
    ],
  },
  {
    name: "Product Squad",
    slug: "product_squad",
    featured: false,
    description:
      "End-to-end product development team with discovery, design, build, test, and ship stages.",
    agents: [
      "Sprint Prioritizer",
      "UX Researcher",
      "Senior Developer x2",
      "Evidence Collector",
      "Project Manager",
    ],
    governance: "Balanced",
    budget: "$80",
    workflow: "Discover > Design > Build > Test > Ship",
    useCases: [
      "Feature development sprints",
      "Product iteration cycles",
      "MVP builds",
      "User-driven redesigns",
    ],
  },
  {
    name: "SaaS Development Studio",
    slug: "saas_dev_studio",
    featured: false,
    description:
      "Full-stack engineering team with architecture, frontend, backend, DevOps, and QA coverage.",
    agents: [
      "Tech Lead",
      "Backend Architect",
      "Frontend Developer",
      "DevOps Automator",
      "Evidence Collector",
      "Project Manager",
    ],
    governance: "Balanced",
    budget: "$100",
    workflow: "Plan > Design > Implement > Test > Deploy",
    useCases: [
      "SaaS product builds",
      "API development",
      "Full-stack feature work",
      "Infrastructure setup",
    ],
  },
  {
    name: "Marketing Agency",
    slug: "marketing_agency",
    featured: false,
    description:
      "Content creation, social media, growth, and brand management team for campaign execution.",
    agents: [
      "Content Creator",
      "Social Media Strategist",
      "Growth Hacker",
      "App Store Optimizer",
      "Brand Guardian",
      "Studio Producer",
    ],
    governance: "Balanced",
    budget: "$75",
    workflow: "Plan > Create > Review > Distribute",
    useCases: [
      "Campaign launches",
      "Content marketing",
      "Social media management",
      "Brand consistency",
    ],
  },
  {
    name: "DevOps Team",
    slug: "devops_team",
    featured: false,
    description:
      "Infrastructure and deployment team with conservative governance for production safety.",
    agents: [
      "DevOps Automator x2",
      "Backend Architect",
      "Performance Benchmarker",
      "Infrastructure Maintainer",
    ],
    governance: "Conservative",
    budget: "$50",
    workflow: "Plan > Build > Test > Deploy > Monitor",
    useCases: [
      "CI/CD pipeline setup",
      "Infrastructure provisioning",
      "Performance optimization",
      "Production monitoring",
    ],
  },
];

interface AIConfig {
  package_name: string;
  display_name: string;
  explanation: string;
  agents: {
    ref: string;
    count: number;
    title?: string;
    bid_strategy: string;
    initial_balance: number;
    domain_tags: string[];
  }[];
  governance_preset: string;
  budget_limit_usd: number;
  follow_up_question?: string | null;
  workflows?: { stages: Record<string, unknown>[] }[];
}

function AIConfigureSection() {
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [config, setConfig] = useState<AIConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleGenerate = async () => {
    if (description.length < 10) return;
    setLoading(true);
    setError(null);
    setConfig(null);

    try {
      const apiKey = sessionStorage.getItem("api_key") || "";
      const resp = await fetch("/api/v1/orgs/configure", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
        body: JSON.stringify({ description }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => null);
        throw new Error(data?.detail || `Request failed (${resp.status})`);
      }

      const data = await resp.json();
      setConfig(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mb-16">
      <div className="rounded-xl border border-[var(--color-accent)]/30 bg-[var(--color-bg-card)] p-8">
        <div className="flex items-center gap-3 mb-4">
          <span className="inline-flex items-center justify-center h-8 w-8 rounded-lg bg-[var(--color-accent)]/20 text-[var(--color-accent)] text-sm font-bold">
            AI
          </span>
          <h2 className="text-xl font-bold">Describe Your Team</h2>
        </div>
        <p className="text-sm text-[var(--color-text-muted)] mb-6">
          Tell us what you want to build or accomplish. Our AI will design a
          custom agent team with the right roles, governance, and workflows.
        </p>

        <div className="space-y-4">
          <textarea
            ref={textareaRef}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. I need a team to build a fintech SaaS product with strict compliance requirements and automated testing..."
            className="w-full h-28 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-accent)] resize-none"
            maxLength={2000}
          />

          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--color-text-dim)]">
              {description.length}/2000
            </span>
            <button
              onClick={handleGenerate}
              disabled={loading || description.length < 10}
              className="rounded-lg bg-[var(--color-accent)] px-6 py-2.5 text-sm font-semibold text-black hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Generating..." : "Generate Team"}
            </button>
          </div>

          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {config && (
            <div className="rounded-lg border border-[var(--color-accent)]/20 bg-[var(--color-bg)] p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold">{config.display_name}</h3>
                <span className="rounded-full border border-[var(--color-border)] px-3 py-1 text-xs text-[var(--color-text-dim)]">
                  ${config.budget_limit_usd}/mo
                </span>
              </div>

              <p className="text-sm text-[var(--color-text-muted)]">
                {config.explanation}
              </p>

              {config.follow_up_question && (
                <div className="rounded-lg border border-[var(--color-accent)]/20 bg-[var(--color-accent)]/5 px-4 py-3 text-sm text-[var(--color-accent)]">
                  {config.follow_up_question}
                </div>
              )}

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)] mb-2">
                  Agents ({config.agents.length})
                </h4>
                <div className="flex flex-wrap gap-2">
                  {config.agents.map((agent, i) => (
                    <span
                      key={i}
                      className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2.5 py-1 text-xs text-[var(--color-text-muted)]"
                    >
                      {agent.title || agent.ref.split("/").pop()?.replace(/-/g, " ")}
                      {agent.count > 1 ? ` x${agent.count}` : ""}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex gap-8">
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)] mb-1">
                    Governance
                  </h4>
                  <span className="text-sm text-[var(--color-text-muted)] capitalize">
                    {config.governance_preset}
                  </span>
                </div>
              </div>

              {config.workflows && config.workflows.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)] mb-2">
                    Workflow
                  </h4>
                  {config.workflows.map((wf, i) => (
                    <div
                      key={i}
                      className="text-xs text-[var(--color-text-dim)] font-mono"
                    >
                      {wf.stages
                        .map((s) => Object.keys(s)[0])
                        .join(" > ")}
                    </div>
                  ))}
                </div>
              )}

              <div className="pt-4 border-t border-[var(--color-border)]">
                <div className="flex gap-3">
                  <button
                    onClick={() => {
                      setConfig(null);
                      setDescription("");
                      textareaRef.current?.focus();
                    }}
                    className="flex-1 rounded-lg border border-[var(--color-border)] px-4 py-2.5 text-sm font-semibold text-[var(--color-text-muted)] hover:border-[var(--color-border-bright)] transition-colors"
                  >
                    Start Over
                  </button>
                  <a
                    href="/signup"
                    className="flex-1 rounded-lg bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-black hover:brightness-110 transition-all text-center"
                  >
                    Deploy This Team
                  </a>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TemplatesClient() {
  const featured = templates.find((t) => t.featured);
  const rest = templates.filter((t) => !t.featured);
  const [copiedSlug, setCopiedSlug] = useState<string | null>(null);

  const handleCopy = async (slug: string) => {
    try {
      const response = await fetch(`/templates/${slug}.yaml`);
      const yamlContent = await response.text();
      await navigator.clipboard.writeText(yamlContent);
      setCopiedSlug(slug);
      setTimeout(() => setCopiedSlug(null), 2000);
    } catch (error) {
      console.error("Failed to copy:", error);
    }
  };

  return (
    <main className="pt-24 pb-16 px-6">
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight">
            Agent Team Templates
          </h1>
          <p className="mt-4 text-lg text-[var(--color-text-muted)] max-w-2xl mx-auto">
            Describe what you need and let AI design your team, or browse
            pre-configured templates ready to deploy.
          </p>
        </div>

        {/* AI Configuration — Primary Path */}
        <AIConfigureSection />

        {/* Divider */}
        <div className="flex items-center gap-4 mb-12">
          <div className="flex-1 h-px bg-[var(--color-border)]" />
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
            Or browse templates
          </span>
          <div className="flex-1 h-px bg-[var(--color-border)]" />
        </div>

        {/* Featured template */}
        {featured && (
          <div className="mb-16">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10 px-4 py-1.5 text-xs text-[var(--color-accent)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]" />
              Featured
            </div>
            <div className="rounded-xl border border-[var(--color-accent)]/30 bg-[var(--color-bg-card)] overflow-hidden">
              <div className="flex flex-col lg:flex-row">
                {/* Left: YAML preview */}
                <div className="flex-1 border-b lg:border-b-0 lg:border-r border-[var(--color-border)]">
                  <div className="flex items-center gap-1.5 border-b border-[var(--color-border)] px-4 py-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
                    <span className="ml-3 text-xs text-[var(--color-text-dim)] font-mono">
                      {featured.slug}.yaml
                    </span>
                  </div>
                  <pre className="p-6 font-mono text-sm leading-relaxed text-[var(--color-text-muted)] overflow-x-auto">
{`apiVersion: agency-os/v1
kind: Package
metadata:
  name: ${featured.slug}

agents:
${featured.agents.map((a) => `  - ${a}`).join("\n")}

governance:
  preset: ${featured.governance.toLowerCase()}

workflows:
  - ${featured.workflow}`}
                  </pre>
                </div>

                {/* Right: details */}
                <div className="flex-1 p-8">
                  <h2 className="text-2xl font-bold mb-3">{featured.name}</h2>
                  <p className="text-[var(--color-text-muted)] mb-6">
                    {featured.description}
                  </p>

                  <div className="space-y-4">
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)] mb-2">
                        Agents
                      </h3>
                      <div className="flex flex-wrap gap-2">
                        {featured.agents.map((agent) => (
                          <span
                            key={agent}
                            className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1 text-xs text-[var(--color-text-muted)]"
                          >
                            {agent}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="flex gap-8">
                      <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)] mb-1">
                          Governance
                        </h3>
                        <span className="text-sm text-[var(--color-text-muted)]">
                          {featured.governance}
                        </span>
                      </div>
                      <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)] mb-1">
                          Budget
                        </h3>
                        <span className="text-sm text-[var(--color-text-muted)]">
                          {featured.budget}/mo
                        </span>
                      </div>
                    </div>

                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)] mb-2">
                        Use Cases
                      </h3>
                      <ul className="space-y-1">
                        {featured.useCases.map((uc) => (
                          <li
                            key={uc}
                            className="text-sm text-[var(--color-text-muted)] flex items-center gap-2"
                          >
                            <span className="text-[var(--color-accent)]">
                              &#10003;
                            </span>
                            {uc}
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="pt-6 border-t border-[var(--color-border)] flex gap-3">
                      <a
                        href={`/templates/${featured.slug}.yaml`}
                        download
                        className="flex-1 rounded-lg bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-black hover:brightness-110 transition-all text-center"
                      >
                        Download YAML
                      </a>
                      <button
                        onClick={() => handleCopy(featured.slug)}
                        className="flex-1 rounded-lg border border-[var(--color-border)] px-4 py-2.5 text-sm font-semibold text-[var(--color-text-muted)] hover:border-[var(--color-border-bright)] transition-colors"
                      >
                        {copiedSlug === featured.slug ? "Copied!" : "Copy YAML"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Template grid */}
        <div className="grid md:grid-cols-2 gap-6">
          {rest.map((template) => (
            <div
              key={template.slug}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 hover:border-[var(--color-border-bright)] transition-colors"
            >
              <h3 className="text-lg font-bold mb-2">{template.name}</h3>
              <p className="text-sm text-[var(--color-text-muted)] mb-4">
                {template.description}
              </p>

              <div className="mb-4">
                <div className="flex flex-wrap gap-1.5">
                  {template.agents.map((agent) => (
                    <span
                      key={agent}
                      className="rounded-md border border-[var(--color-border)] px-2 py-0.5 text-xs text-[var(--color-text-dim)]"
                    >
                      {agent}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-6 text-xs text-[var(--color-text-dim)]">
                <span>
                  Governance:{" "}
                  <span className="text-[var(--color-text-muted)]">
                    {template.governance}
                  </span>
                </span>
                <span>
                  Budget:{" "}
                  <span className="text-[var(--color-text-muted)]">
                    {template.budget}/mo
                  </span>
                </span>
              </div>

              <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
                <div className="text-xs text-[var(--color-text-dim)] font-mono mb-4">
                  {template.workflow}
                </div>
                <div className="flex gap-2">
                  <a
                    href={`/templates/${template.slug}.yaml`}
                    download
                    className="flex-1 rounded-lg bg-[var(--color-accent)] px-3 py-2 text-xs font-semibold text-black hover:brightness-110 transition-all text-center"
                  >
                    Download
                  </a>
                  <button
                    onClick={() => handleCopy(template.slug)}
                    className="flex-1 rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs font-semibold text-[var(--color-text-muted)] hover:border-[var(--color-border-bright)] transition-colors"
                  >
                    {copiedSlug === template.slug ? "Copied!" : "Copy"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* CTA */}
        <div className="mt-16 text-center">
          <p className="text-[var(--color-text-muted)] mb-4">
            Each template is a single YAML file. Customize agents, governance,
            and budgets to fit your needs.
          </p>
          <div className="flex items-center justify-center gap-4">
            <a
              href="/quickstart"
              className="rounded-lg bg-[var(--color-accent)] px-6 py-2.5 text-sm font-semibold text-black hover:brightness-110 transition-all"
            >
              Get Started
            </a>
            <a
              href="/#waitlist"
              className="rounded-lg border border-[var(--color-border)] px-6 py-2.5 text-sm font-semibold text-[var(--color-text-muted)] hover:border-[var(--color-border-bright)] transition-colors"
            >
              Join Waitlist
            </a>
          </div>
        </div>
      </div>
    </main>
  );
}
