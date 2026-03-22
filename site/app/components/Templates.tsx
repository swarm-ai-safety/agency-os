export default function Templates() {
  const templates = [
    {
      name: "Product Squad",
      description: "End-to-end product team with PM, UX researcher, and senior developers. Quality-weighted bidding for balanced velocity and polish.",
      agents: ["Product Manager", "UX Researcher", "Senior Developers"],
      slug: "product_squad"
    },
    {
      name: "Marketing Agency",
      description: "Full-service content and growth team. Content creators, social strategists, and growth hackers with coordinated campaigns.",
      agents: ["Content Creator", "Social Media Strategist", "Growth Hacker"],
      slug: "marketing_agency"
    },
    {
      name: "DevOps Team",
      description: "Infrastructure automation and deployment pipeline management. SREs, security specialists, and CI/CD automation.",
      agents: ["SRE", "Security Engineer", "Automation Specialist"],
      slug: "devops_team"
    }
  ];

  return (
    <section id="templates" className="py-24 bg-[var(--color-bg-alt)]">
      <div className="mx-auto max-w-6xl px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
            Pre-Built Agent Teams
          </h2>
          <p className="text-lg text-[var(--color-text-muted)] max-w-2xl mx-auto">
            Skip the setup. Deploy proven agent team configurations with governance built-in.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6 mb-12">
          {templates.map((template) => (
            <div
              key={template.slug}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-6 hover:border-[var(--color-accent)] transition-all group"
            >
              <h3 className="text-xl font-semibold mb-3 group-hover:text-[var(--color-accent)] transition-colors">
                {template.name}
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] mb-4 leading-relaxed">
                {template.description}
              </p>
              <div className="flex flex-wrap gap-2">
                {template.agents.map((agent) => (
                  <span
                    key={agent}
                    className="px-2 py-1 text-xs rounded-md bg-[var(--color-bg-alt)] text-[var(--color-text-muted)] border border-[var(--color-border)]"
                  >
                    {agent}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="text-center">
          <a
            href="/templates"
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-6 py-3 text-sm font-semibold text-black hover:brightness-110 transition-all"
          >
            Browse All Templates
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </a>
        </div>
      </div>
    </section>
  );
}
