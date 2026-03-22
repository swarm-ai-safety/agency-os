import { getCommunityCtaConfig } from "./community-cta";

export default function Community() {
  const cta = getCommunityCtaConfig();

  return (
    <section id="community" className="py-24 px-6 border-t border-[var(--color-border)]">
      <div className="mx-auto max-w-6xl">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Built for solo founders and small teams
          </h2>
          <p className="mt-4 text-[var(--color-text-muted)] max-w-2xl mx-auto">
            You don&apos;t need a 50-person company to build a 50-person product.
            Join founders who are replacing headcount with agent teams.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8 hover:border-[var(--color-border-bright)] transition-colors">
            <div className="text-2xl mb-4">01</div>
            <h3 className="text-lg font-bold mb-2">Ship Faster Alone</h3>
            <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
              Launch a dev studio, marketing agency, or product squad from one
              config file. Your agents handle execution while you handle
              vision.
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8 hover:border-[var(--color-border-bright)] transition-colors">
            <div className="text-2xl mb-4">02</div>
            <h3 className="text-lg font-bold mb-2">Builder Community</h3>
            <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
              {cta.body}
            </p>
            <a
              href={cta.href}
              target={cta.isLiveDiscord ? "_blank" : undefined}
              rel={cta.isLiveDiscord ? "noopener noreferrer" : undefined}
              className="inline-block mt-4 text-sm font-medium text-[var(--color-accent)] hover:underline"
            >
              {cta.label}
            </a>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8 hover:border-[var(--color-border-bright)] transition-colors">
            <div className="text-2xl mb-4">03</div>
            <h3 className="text-lg font-bold mb-2">Research-Backed Defaults</h3>
            <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
              Every governance lever is calibrated from real simulation data.
              84 empirical claims, 146 runs &mdash; no guesswork, no black
              boxes.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
