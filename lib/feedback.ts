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
const OWNER_KEY = "digest:owner-key";
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

/** The owner unlocks vote syncing once per browser by visiting
 * /?owner=<FEEDBACK_KEY>. The key is kept in localStorage and scrubbed from
 * the address bar so it doesn't end up in history or a shared link. */
function ownerKey(): string | null {
  try {
    const url = new URL(window.location.href);
    const fromUrl = url.searchParams.get("owner");
    if (fromUrl) {
      window.localStorage.setItem(OWNER_KEY, fromUrl);
      url.searchParams.delete("owner");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
      return fromUrl;
    }
    return window.localStorage.getItem(OWNER_KEY);
  } catch {
    return null;
  }
}

/** Client-side like/dislike: instant local re-ranking via localStorage for
 * everyone. For the owner (see ownerKey), each vote is also synced to
 * /api/feedback so the nightly pipeline learns the same preference. */
export function useFeedback() {
  const [votes, setVotes] = useState<Votes>({});
  const [key, setKey] = useState<string | null>(null);

  useEffect(() => {
    setVotes(readVotes());
    setKey(ownerKey());
  }, []);

  const castVote = useCallback(
    (id: string, tag: string, source: string, title: string, value: 1 | -1) => {
      setVotes((prev) => {
        const next = { ...prev };
        const clearing = next[id]?.vote === value;
        if (clearing) {
          delete next[id];
        } else {
          next[id] = { vote: value, tag, source, ts: new Date().toISOString() };
        }
        writeVotes(next);
        if (key) {
          // Trailing slash avoids an extra 308 from next.config's trailingSlash.
          fetch("/api/feedback/", {
            method: "POST",
            headers: { "Content-Type": "application/json", "x-feedback-key": key },
            body: JSON.stringify({ id, tag, source, title, vote: clearing ? 0 : value }),
          }).catch(() => {
            /* best-effort; localStorage already has the vote either way */
          });
        }
        return next;
      });
    },
    [key],
  );

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

  return { castVote, getVote, boost, syncing: Boolean(key) };
}
