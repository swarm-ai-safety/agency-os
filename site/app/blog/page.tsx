import type { Metadata } from "next";
import Link from "next/link";

import { getAllPosts } from "../lib/blog";

export const metadata: Metadata = {
  title: "Blog — Zero Human Labs",
  description:
    "Research, engineering insights, and lessons from building autonomous AI companies.",
  alternates: {
    canonical: "/blog",
  },
  openGraph: {
    url: "/blog",
  },
};

export default function BlogIndex() {
  const posts = getAllPosts();

  return (
    <main className="mx-auto max-w-3xl px-4 py-24 sm:px-6">
      <h1 className="text-4xl font-bold tracking-tight">Blog</h1>
      <p className="mt-3 text-lg text-[var(--color-text-muted)]">
        Research, engineering insights, and lessons from building autonomous AI
        companies.
      </p>

      {posts.length === 0 ? (
        <p className="mt-12 text-[var(--color-text-muted)]">
          No posts yet. Check back soon.
        </p>
      ) : (
        <div className="mt-12 space-y-8">
          {posts.map((post) => (
            <article
              key={post.slug}
              className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 transition-colors hover:border-[var(--color-border-bright)]"
            >
              <Link href={`/blog/${post.slug}`} className="block">
                <h2 className="text-xl font-bold leading-snug hover:text-[var(--color-accent)] transition-colors">
                  {post.title}
                </h2>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  {post.description}
                </p>
                <div className="mt-4 flex items-center gap-3 text-xs text-[var(--color-text-dim)]">
                  <time dateTime={post.date}>
                    {new Date(post.date).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </time>
                  <span>·</span>
                  <span>{post.author}</span>
                </div>
                {post.tags.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {post.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-md bg-[var(--color-bg)] px-2 py-0.5 text-xs text-[var(--color-text-muted)]"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </Link>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
