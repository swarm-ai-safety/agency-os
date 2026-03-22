import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import Nav from "../../components/Nav";
import Footer from "../../components/Footer";
import { getAllDocSlugs, getDocBySlug, getDocNavGroups } from "../../lib/docs";

interface Props {
  params: Promise<{ slug: string[] }>;
}

export async function generateStaticParams() {
  return getAllDocSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const doc = await getDocBySlug(slug);
  if (!doc) return {};
  return {
    title: `${doc.title} — Docs — Zero Human Labs`,
    description: doc.description || `${doc.title} documentation for Agency-OS.`,
    alternates: { canonical: `/docs/${slug.join("/")}` },
  };
}

export default async function DocPage({ params }: Props) {
  const { slug } = await params;
  const doc = await getDocBySlug(slug);
  if (!doc) notFound();

  const groups = getDocNavGroups();
  const currentPath = slug.join("/");

  return (
    <>
      <Nav />
      <div className="mx-auto max-w-6xl px-4 pt-24 pb-16 sm:px-6 lg:flex lg:gap-10">
        {/* Sidebar */}
        <aside className="hidden lg:block lg:w-56 shrink-0">
          <nav className="sticky top-24 max-h-[calc(100vh-8rem)] overflow-y-auto pb-8">
            <Link
              href="/docs"
              className="text-xs uppercase tracking-[0.16em] text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] transition-colors"
            >
              Documentation
            </Link>
            <div className="mt-4 space-y-6">
              {groups.map((group) => (
                <div key={group.label}>
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)] mb-2">
                    {group.label}
                  </p>
                  <ul className="space-y-1">
                    {group.items.map((item) => {
                      const itemPath = item.slug.join("/");
                      const isActive = itemPath === currentPath;
                      return (
                        <li key={itemPath}>
                          <Link
                            href={`/docs/${itemPath}`}
                            className={`block rounded-md px-2 py-1.5 text-sm transition-colors ${
                              isActive
                                ? "bg-[var(--color-bg-card)] text-[var(--color-accent)] font-medium"
                                : "text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg-card)]"
                            }`}
                          >
                            {item.title}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </nav>
        </aside>

        {/* Mobile sidebar toggle + breadcrumb */}
        <main className="min-w-0 flex-1">
          <div className="mb-6 flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <Link
              href="/docs"
              className="hover:text-[var(--color-text)] transition-colors"
            >
              Docs
            </Link>
            {slug.length > 1 && (
              <>
                <span>/</span>
                <span className="capitalize">{slug[0]}</span>
              </>
            )}
            <span>/</span>
            <span className="text-[var(--color-text)]">{doc.title}</span>
          </div>

          <article>
            <h1 className="text-3xl font-bold tracking-tight sm:text-4xl mb-8">
              {doc.title}
            </h1>

            <div
              className="prose prose-invert max-w-none
                [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:mt-10 [&_h1]:mb-4
                [&_h2]:text-xl [&_h2]:font-bold [&_h2]:mt-8 [&_h2]:mb-3
                [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:mt-6 [&_h3]:mb-2
                [&_p]:text-[var(--color-text-muted)] [&_p]:leading-relaxed [&_p]:mb-4
                [&_strong]:text-[var(--color-text)] [&_strong]:font-semibold
                [&_a]:text-[var(--color-accent)] [&_a]:underline [&_a]:underline-offset-2 hover:[&_a]:brightness-110
                [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:mb-4 [&_ul]:space-y-1
                [&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:mb-4 [&_ol]:space-y-1
                [&_li]:text-[var(--color-text-muted)]
                [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--color-accent-dim)] [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-[var(--color-text-dim)] [&_blockquote]:my-4
                [&_code]:bg-[var(--color-bg-card)] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-sm [&_code]:font-mono
                [&_pre]:bg-[var(--color-bg-card)] [&_pre]:border [&_pre]:border-[var(--color-border)] [&_pre]:rounded-xl [&_pre]:p-4 [&_pre]:overflow-x-auto [&_pre]:mb-4
                [&_hr]:border-[var(--color-border)] [&_hr]:my-8
                [&_table]:w-full [&_table]:border-collapse [&_table]:mb-4
                [&_th]:border [&_th]:border-[var(--color-border)] [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold
                [&_td]:border [&_td]:border-[var(--color-border)] [&_td]:px-3 [&_td]:py-2 [&_td]:text-[var(--color-text-muted)]"
              dangerouslySetInnerHTML={{ __html: doc.content }}
            />
          </article>
        </main>
      </div>
      <Footer />
    </>
  );
}
