export default function CaseStudy() {
  return (
    <section
      id="case-study"
      className="py-24 px-6 border-t border-[var(--color-border)]"
    >
      <div className="mx-auto max-w-6xl">
        <div className="text-center mb-16">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-1.5 text-xs text-[var(--color-text-muted)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]" />
            Real-world demo
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Agents doing real research, not toy demos
          </h2>
          <p className="mt-4 text-[var(--color-text-muted)] max-w-2xl mx-auto">
            We orchestrated a team of{" "}
            <a
              href="https://nousresearch.com/hermes-agent/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-accent)] hover:underline"
            >
              NousResearch Hermes Agents
            </a>{" "}
            to conduct biotech research &mdash; analyzing peer-reviewed
            immunotherapy literature and synthesizing a novel clinical AI
            proposal.
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          {/* Left: the setup */}
          <div className="flex-1 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] overflow-hidden">
            <div className="flex items-center gap-1.5 border-b border-[var(--color-border)] px-4 py-2">
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-text-dim)]/30" />
              <span className="ml-3 text-xs text-[var(--color-text-dim)] font-mono">
                SwarmScholar &middot; Multi-Agent Research Swarm
              </span>
            </div>
            <div className="p-6 font-mono text-sm leading-relaxed space-y-3">
              <div className="text-[var(--color-text-dim)]">
                # Orchestrated via Agency-OS
              </div>
              <div className="text-[var(--color-text-muted)]">
                <span className="text-[var(--color-accent)]">Task:</span>{" "}
                Analyze immunotherapy patient selection literature
              </div>
              <div className="text-[var(--color-text-muted)]">
                <span className="text-[var(--color-accent)]">Agents:</span>{" "}
                Hermes research swarm (literature review, synthesis, critique)
              </div>
              <div className="text-[var(--color-text-muted)]">
                <span className="text-[var(--color-accent)]">Sources:</span> 8
                key papers + reviews + regulatory docs
              </div>
              <div className="mt-4 border-t border-[var(--color-border)] pt-4">
                <div className="text-[var(--color-text-dim)]"># Output</div>
                <div className="text-[var(--color-text-muted)]">
                  <span className="text-[var(--color-accent)]">&#10003;</span>{" "}
                  Tiered escalation architecture for clinical AI
                </div>
                <div className="text-[var(--color-text-muted)]">
                  <span className="text-[var(--color-accent)]">&#10003;</span>{" "}
                  Novel proposal: blood-test triage first, deep learning second
                </div>
                <div className="text-[var(--color-text-muted)]">
                  <span className="text-[var(--color-accent)]">&#10003;</span>{" "}
                  Critical gap identified across all reviewed models
                </div>
              </div>
            </div>
          </div>

          {/* Right: the results */}
          <div className="flex-1 space-y-5">
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 hover:border-[var(--color-border-bright)] transition-colors">
              <h3 className="text-base font-bold mb-2">
                3-tier clinical AI architecture
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
                Agents synthesized evidence from competing models (SCORPIO,
                MuMo, genomic classifiers) into a deployable tiered system
                &mdash; blood tests at community hospitals, full multi-modal
                transformers at academic centers.
              </p>
            </div>

            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 hover:border-[var(--color-border-bright)] transition-colors">
              <h3 className="text-base font-bold mb-2">
                Real literature, not hallucinations
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
                The swarm analyzed actual peer-reviewed papers, cross-referenced
                AUC scores (0.763 to 0.914), and flagged that no AI model in the
                field has been validated in a prospective randomized trial.
              </p>
            </div>

            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 hover:border-[var(--color-border-bright)] transition-colors">
              <h3 className="text-base font-bold mb-2">
                Orchestration handled the hard part
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
                Multiple agents coordinated literature search, evidence
                synthesis, and critical analysis &mdash; the orchestrator managed
                task routing, agent coordination, and output assembly
                automatically.
              </p>
            </div>

            <div className="text-center pt-2">
              <a
                href="https://beach.science/post/43e2337c-ef98-4c67-8190-a19af8197617"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-[var(--color-accent)] hover:underline"
              >
                Read the full research output &rarr;
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
