import type { Metadata } from "next";
import Link from "next/link";

import Nav from "../components/Nav";
import Footer from "../components/Footer";
import { getDocNavGroups } from "../lib/docs";

export const metadata: Metadata = {
  title: "Documentation — Zero Human Labs",
  description:
    "Technical documentation for Agency-OS: API reference, deployment, governance, and operations guides.",
  alternates: { canonical: "/docs" },
};

export default function DocsIndexPage() {
  const groups = getDocNavGroups();

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-4xl px-4 py-24 sm:px-6">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Documentation
        </h1>
        <p className="mt-3 text-[var(--color-text-muted)] max-w-2xl">
          Technical guides for Agency-OS — API reference, deployment,
          governance, operations, and more.
        </p>

        <div className="mt-12 space-y-10">
          {groups.map((group) => (
            <section key={group.label}>
              <h2 className="text-lg font-semibold mb-4 text-[var(--color-text)]">
                {group.label}
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {group.items.map((doc) => (
                  <Link
                    key={doc.slug.join("/")}
                    href={`/docs/${doc.slug.join("/")}`}
                    className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3 hover:border-[var(--color-border-bright)] transition-colors group"
                  >
                    <span className="text-sm font-medium text-[var(--color-text)] group-hover:text-[var(--color-accent)] transition-colors">
                      {doc.title}
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>
      <Footer />
    </>
  );
}
