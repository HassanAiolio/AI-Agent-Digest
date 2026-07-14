"use client";
import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "digest:read:v1";
const MAX_ENTRIES = 1000;

type ReadMap = Record<string, number>; // id -> timestamp, for LRU trimming

function readMap(): ReadMap {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function writeMap(map: ReadMap) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // storage full/unavailable — read state just won't persist this session
  }
}

/** Tracks which items you've already opened, purely client-side, so a
 * returning visitor can tell at a glance what's new since last time. */
export function useReadState() {
  const [read, setRead] = useState<ReadMap>({});

  useEffect(() => {
    setRead(readMap());
  }, []);

  const markRead = useCallback((id: string) => {
    setRead((prev) => {
      if (prev[id]) return prev;
      let next = { ...prev, [id]: Date.now() };
      const keys = Object.keys(next);
      if (keys.length > MAX_ENTRIES) {
        keys.sort((a, b) => next[a] - next[b]);
        for (const k of keys.slice(0, keys.length - MAX_ENTRIES)) delete next[k];
      }
      writeMap(next);
      return next;
    });
  }, []);

  const isRead = useCallback((id: string) => Boolean(read[id]), [read]);

  return { isRead, markRead };
}
