"use client";
import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "digest:theme";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Manual override for the site's default prefers-color-scheme theming.
 * The actual no-flash application on page load happens via an inline
 * script in layout.tsx (runs before paint); this component just lets you
 * flip it and persists the choice. */
export default function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const [theme, setTheme] = useState<Theme | null>(null); // null = follow system

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    setTheme(stored === "light" || stored === "dark" ? stored : null);
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <button type="button" className="theme-toggle" aria-label="Toggle theme" disabled>
        ◐
      </button>
    );
  }

  const effective: Theme = theme ?? (systemPrefersDark() ? "dark" : "light");

  function toggle() {
    const next: Theme = effective === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // storage full/unavailable — theme just won't persist across visits
    }
  }

  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label="Toggle theme">
      {effective === "dark" ? "☀" : "☾"}
    </button>
  );
}
