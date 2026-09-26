"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import SearchPalette from "./SearchPalette";
import ThemeToggle from "./ThemeToggle";

const NAV = [
  { href: "/", label: "Today" },
  { href: "/weekly/", label: "Weekly" },
  { href: "/archive/", label: "Archive" },
  { href: "/health/", label: "Health" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href.replace(/\/$/, ""));
}

export default function SiteHeader({ latestDate }: { latestDate: string }) {
  const pathname = usePathname() || "/";
  const [searchOpen, setSearchOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);

  // Reading progress: written straight to a transform on a rAF, so scrolling
  // never re-renders React.
  useEffect(() => {
    let frame = 0;
    function update() {
      frame = 0;
      const el = document.documentElement;
      const max = el.scrollHeight - el.clientHeight;
      const p = max > 0 ? Math.min(1, el.scrollTop / max) : 0;
      if (barRef.current) barRef.current.style.transform = `scaleX(${p})`;
      setScrolled(el.scrollTop > 8);
    }
    function onScroll() {
      if (!frame) frame = requestAnimationFrame(update);
    }
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [pathname]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      const typing = t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.isContentEditable;
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setSearchOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <header className={scrolled ? "topbar topbar-scrolled" : "topbar"}>
        <div className="topbar-inner">
          <Link href="/" className="wordmark" aria-label="Nightly digest, today's edition">
            <span className="wordmark-dot" aria-hidden="true" />
            Nightly
          </Link>
          <nav className="topnav" aria-label="Primary">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={isActive(pathname, n.href) ? "active" : undefined}
                aria-current={isActive(pathname, n.href) ? "page" : undefined}
              >
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="topbar-actions">
            <button type="button" className="search-trigger" onClick={() => setSearchOpen(true)}>
              <svg aria-hidden="true" viewBox="0 0 16 16" width="14" height="14">
                <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
                <path d="M10.5 10.5 14 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
              <span className="search-trigger-label">Search</span>
              <kbd>⌘K</kbd>
            </button>
            <ThemeToggle />
          </div>
        </div>
        <div className="progress" aria-hidden="true">
          <div ref={barRef} className="progress-bar" />
        </div>
      </header>
      <SearchPalette open={searchOpen} onClose={() => setSearchOpen(false)} latestDate={latestDate} />
    </>
  );
}
