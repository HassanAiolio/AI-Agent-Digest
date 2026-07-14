"use client";
import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "digest:collapsed-sections:v1";

function read(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

/** Which sections you've folded shut, e.g. hiding "Competitive programming"
 * on nights you don't care — persisted so it stays folded next visit. */
export function useCollapsedSections() {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setCollapsed(read());
  }, []);

  const toggle = useCallback((id: string) => {
    setCollapsed((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // storage full/unavailable — collapse state just won't persist
      }
      return next;
    });
  }, []);

  return { collapsed, toggle };
}
