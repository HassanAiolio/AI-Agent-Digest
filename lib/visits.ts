"use client";
import { useEffect, useState } from "react";

const STORAGE_KEY = "digest:visits:v1";

interface VisitState {
  last: string; // YYYY-MM-DD, local
  streak: number; // consecutive days with a visit, ending at `last`
  best: number;
}

export interface VisitInfo {
  streak: number;
  best: number;
  /** Local date of the previous visit (before today), or null on a first visit. */
  previous: string | null;
}

function localDay(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function dayDiff(a: string, b: string): number {
  return Math.round((Date.parse(b + "T12:00:00") - Date.parse(a + "T12:00:00")) / 86_400_000);
}

/** Reading streak, kept in this browser only. Counts calendar days with at
 * least one visit; missing a day resets it. */
export function useVisits(): VisitInfo | null {
  const [info, setInfo] = useState<VisitInfo | null>(null);

  useEffect(() => {
    const today = localDay();
    let prev: VisitState | null = null;
    try {
      prev = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null");
    } catch {
      prev = null;
    }

    let next: VisitState;
    let previous: string | null = null;
    if (!prev?.last) {
      next = { last: today, streak: 1, best: 1 };
    } else if (prev.last === today) {
      next = prev;
      // Keep reporting the visit before today across reloads.
      previous = (prev as VisitState & { before?: string }).before ?? null;
    } else {
      previous = prev.last;
      const streak = dayDiff(prev.last, today) === 1 ? prev.streak + 1 : 1;
      next = { last: today, streak, best: Math.max(prev.best ?? 1, streak) };
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...next, before: previous }));
    } catch {
      // storage unavailable — streak just won't persist
    }
    setInfo({ streak: next.streak, best: next.best, previous });
  }, []);

  return info;
}
