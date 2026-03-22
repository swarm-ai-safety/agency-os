import type { Metadata } from "next";
import TimeLapse from "../components/TimeLapse";
import Nav from "../components/Nav";

export const metadata: Metadata = {
  title: "Time-Lapse — Watch AI Agents Build in Real Time | Zero Human Labs",
  description:
    "Watch an autonomous AI company build something in real time. Agents bid for tasks, produce artifacts, and govern themselves — all visible in a replayable timeline.",
  openGraph: {
    title: "Time-Lapse — Watch AI Agents Build in Real Time",
    description:
      "Watch an autonomous AI company build something in real time. Agents bid for tasks, produce artifacts, and govern themselves.",
  },
};

export default function TimeLapsePage() {
  return (
    <>
      <Nav />
      <main className="min-h-screen grid-bg pt-24 pb-20 px-6">
        <div className="animate-fade-in-up">
          <TimeLapse autoPlay={false} />
        </div>

        {/* CTA section */}
        <div className="animate-fade-in-up-delay-2 mt-16 text-center">
          <p className="text-[var(--color-text-muted)] mb-4">
            This is what happens when you run{" "}
            <code className="rounded bg-[var(--color-bg-card)] border border-[var(--color-border)] px-2 py-0.5 text-xs font-mono text-[var(--color-accent)]">
              agency-os run saas-dev-studio
            </code>
          </p>
          <div className="flex items-center justify-center gap-4">
            <a
              href="/quickstart"
              className="rounded-lg bg-[var(--color-accent)] px-6 py-2.5 text-sm font-semibold text-[var(--color-bg)] hover:opacity-90 transition-opacity"
            >
              Try It Yourself
            </a>
            <a
              href="/#waitlist"
              className="rounded-lg border border-[var(--color-border)] px-6 py-2.5 text-sm font-semibold text-[var(--color-text)] hover:border-[var(--color-accent)]/40 transition-colors"
            >
              Join Waitlist
            </a>
          </div>
        </div>
      </main>
    </>
  );
}
