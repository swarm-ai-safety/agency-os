"use client";

import { useEffect, useMemo, useState } from "react";

const links = [
  { href: "#platform", label: "Platform" },
  { href: "/docs", label: "Docs" },
  { href: "/blog", label: "Blog" },
  { href: "/timelapse", label: "Time-Lapse" },
  { href: "#pricing", label: "Pricing" },
  { href: "/templates", label: "Templates" },
  { href: "#proof", label: "Research" },
  { href: "#community", label: "Community" },
];

export default function Nav() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeSection, setActiveSection] = useState<string>("#");

  const sectionAnchors = useMemo(
    () => links.filter((link) => link.href.startsWith("#")).map((link) => link.href),
    [],
  );

  useEffect(() => {
    function syncActiveSection() {
      const midpoint = window.scrollY + window.innerHeight * 0.35;
      let current = "#";

      for (const anchor of sectionAnchors) {
        if (anchor === "#") {
          continue;
        }
        const section = document.querySelector(anchor);
        if (!section) {
          continue;
        }
        const top = (section as HTMLElement).offsetTop;
        if (midpoint >= top - 80) {
          current = anchor;
        }
      }

      setActiveSection(current);
    }

    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    }

    syncActiveSection();
    window.addEventListener("scroll", syncActiveSection, { passive: true });
    window.addEventListener("resize", syncActiveSection);
    window.addEventListener("keydown", onEscape);
    return () => {
      window.removeEventListener("scroll", syncActiveSection);
      window.removeEventListener("resize", syncActiveSection);
      window.removeEventListener("keydown", onEscape);
    };
  }, [sectionAnchors]);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  function closeMenu() {
    setMenuOpen(false);
  }

  function isActiveLink(href: string) {
    return href.startsWith("#") ? href === activeSection : false;
  }

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)]/75 backdrop-blur-xl">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-transparent via-[var(--color-accent-glow)]/25 to-transparent" />
      <div className="relative mx-auto max-w-6xl flex items-center justify-between px-4 py-3 sm:px-6">
        <a href="#" className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-[var(--color-accent)] shadow-[0_0_24px_var(--color-accent-glow)] flex items-center justify-center">
            <span className="text-sm font-bold text-black">0H</span>
          </div>
          <span className="text-base sm:text-lg font-bold tracking-tight">
            Zero Human Labs
          </span>
        </a>

        <div className="hidden md:flex items-center gap-1 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)]/70 p-1 text-sm">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className={`rounded-lg px-3 py-2 transition-colors ${
                isActiveLink(link.href)
                  ? "bg-[var(--color-bg)] text-[var(--color-text)]"
                  : "text-[var(--color-text-muted)] hover:bg-[var(--color-bg)] hover:text-[var(--color-text)]"
              }`}
            >
              {link.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="md:hidden rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-bright)] transition-colors"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav-menu"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
          >
            {menuOpen ? "Close" : "Menu"}
          </button>
          <a
            href="/login"
            className="hidden sm:inline-flex rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-bright)] transition-colors"
          >
            Log In
          </a>
          <a
            href="/signup"
            className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-black hover:brightness-110 shadow-[0_0_24px_var(--color-accent-glow)] transition-all"
          >
            Sign Up
          </a>
        </div>
      </div>

      {menuOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={closeMenu}
          aria-label="Close mobile navigation"
        />
      )}

      {menuOpen && (
        <div
          id="mobile-nav-menu"
          className="absolute left-0 right-0 z-50 md:hidden border-t border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-xl"
        >
          <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6">
            <p className="mb-3 text-xs uppercase tracking-[0.16em] text-[var(--color-text-dim)]">
              Navigate
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {links.map((link) => (
                <a
                  key={`mobile-${link.href}`}
                  href={link.href}
                  onClick={closeMenu}
                  className={`rounded-lg border bg-[var(--color-bg)] px-3 py-2.5 text-sm transition-colors ${
                    isActiveLink(link.href)
                      ? "border-[var(--color-accent-dim)] text-[var(--color-text)]"
                      : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-bright)]"
                  }`}
                >
                  {link.label}
                </a>
              ))}
            </div>
            <a
              href="https://github.com/swarm-ai-safety/swarm"
              target="_blank"
              rel="noopener noreferrer"
              onClick={closeMenu}
              className="mt-3 block rounded-lg border border-[var(--color-border)] px-3 py-2.5 text-center text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-bright)] transition-colors"
            >
              View GitHub
            </a>
            <a
              href="/login"
              onClick={closeMenu}
              className="mt-2 block rounded-lg border border-[var(--color-border)] px-3 py-2.5 text-center text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-bright)] transition-colors"
            >
              Log In
            </a>
            <a
              href="/signup"
              onClick={closeMenu}
              className="mt-2 block rounded-lg bg-[var(--color-accent)] px-3 py-2.5 text-center text-sm font-semibold text-black hover:brightness-110 transition-all"
            >
              Create Account
            </a>
          </div>
        </div>
      )}
    </nav>
  );
}
