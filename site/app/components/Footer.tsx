export default function Footer() {
  return (
    <footer className="border-t border-[var(--color-border)] py-12 px-6">
      <div className="mx-auto max-w-6xl flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-md bg-[var(--color-accent)] flex items-center justify-center">
            <span className="text-xs font-bold text-black">0H</span>
          </div>
          <span className="text-sm font-semibold">Zero Human Labs</span>
        </div>

        <div className="flex items-center gap-6 text-sm text-[var(--color-text-dim)]">
          <a
            href="/docs"
            className="hover:text-[var(--color-text-muted)] transition-colors"
          >
            Docs
          </a>
          <a
            href="/blog"
            className="hover:text-[var(--color-text-muted)] transition-colors"
          >
            Blog
          </a>
          <a
            href="/docs/api-reference"
            className="hover:text-[var(--color-text-muted)] transition-colors"
          >
            API Reference
          </a>
          <a
            href="https://github.com/swarm-ai-safety/swarm"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-[var(--color-text-muted)] transition-colors"
          >
            GitHub
          </a>
          <a
            href="https://swarm-ai.org"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-[var(--color-text-muted)] transition-colors"
          >
            Research
          </a>
          <span>&copy; {new Date().getFullYear()} Zero Human Labs</span>
        </div>
      </div>
    </footer>
  );
}
