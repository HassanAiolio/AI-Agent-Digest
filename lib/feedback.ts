"use client";
import { useCallback, useEffect, useMemo, useState } from "react";

export interface Vote {
  vote: 1 | -1;
  tag: string;
  source: string;
  ts: string;
}

type Votes = Record<string, Vote>;

const STORAGE_KEY = "digest:feedback:v1";
const CLAMP = 3;
const TAG_WEIGHT = 0.6;
const SOURCE_WEIGHT = 0.4;

function readVotes(): Votes {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function writeVotes(votes: Votes) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(votes));
  } catch {
    // storage full or unavailable (private browsing) — vote just won't persist
  }
}

/** Client-side like/dislike: instant local re-ranking via localStorage, plus
 * a best-effort sync to /api/feedback so the nightly pipeline can learn the
 * same preference server-side (see pipeline/preferences.py). If the sync
 * fails or the endpoint isn't configured, the local vote still applies —
 * syncing is a bonus, never a requirement for the feature to work. */
export function useFeedback() {
  const [votes, setVotes] = useState<Votes>({});

  useEffect(() => {
    setVotes(readVotes());
  }, []);

  const castVote = useCallback((id: string, tag: string, source: string, value: 1 | -1) => {
    setVotes((prev) => {
      const next = { ...prev };
      const clearing = next[id]?.vote === value;
      if (clearing) {
        delete next[id];
      } else {
        next[id] = { vote: value, tag, source, ts: new Date().toISOString() };
      }
      writeVotes(next);
      // Trailing slash avoids an extra 308-redirect hop from next.config's
      // trailingSlash: true (which applies to route handlers too).
      fetch("/api/feedback/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, tag, source, vote: clearing ? 0 : value }),
      }).catch(() => {
        /* best-effort; localStorage already has the vote either way */
      });
      return next;
    });
  }, []);

  const affinity = useMemo(() => {
    const tags: Record<string, number> = {};
    const sources: Record<string, number> = {};
    for (const v of Object.values(votes)) {
      if (v.tag) tags[v.tag] = (tags[v.tag] ?? 0) + v.vote;
      if (v.source) sources[v.source] = (sources[v.source] ?? 0) + v.vote;
    }
    const clamp = (n: number) => Math.max(-CLAMP, Math.min(CLAMP, n));
    for (const k in tags) tags[k] = clamp(tags[k]);
    for (const k in sources) sources[k] = clamp(sources[k]);
    return { tags, sources };
  }, [votes]);

  const boost = useCallback(
    (tag: string, source: string) =>
      (affinity.tags[tag] ?? 0) * TAG_WEIGHT + (affinity.sources[source] ?? 0) * SOURCE_WEIGHT,
    [affinity],
  );

  const getVote = useCallback((id: string) => votes[id]?.vote, [votes]);

  return { castVote, getVote, boost };
}
