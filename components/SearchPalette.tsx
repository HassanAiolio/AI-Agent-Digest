"use client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SearchEntry } from "@/app/search-index.json/route";

const LIMIT = 40;

let indexPromise: Promise<SearchEntry[]> | null = null;
function loadIndex(): Promise<SearchEntry[]> {
  if (!indexPromise) {
    indexPromise = fetch("/search-index.json")
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => {
        indexPromise = null; // allow a retry on the next open
        return [];
      });
  }
  return indexPromise;
}

function fold(s: string): string {
  return s.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

/** Every query word must appear somewhere; title hits outrank summary hits,
 * and newer editions win ties. Plain substring matching is plenty for a few
 * thousand short entries and needs no library. */
function search(index: SearchEntry[], query: string): SearchEntry[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const scored: { e: SearchEntry; score: number }[] = [];
  for (const e of index) {
    const title = fold(e.t);
    const rest = fold(`${e.s} ${e.o} ${e.g} ${e.c}`);
    let score = 0;
    let ok = true;
    for (const w of words) {
      if (title.includes(w)) score += title.startsWith(w) || title.includes(` ${w}`) ? 3 : 2;
      else if (rest.includes(w)) score += 1;
      else {
        ok = false;
        break;
      }
    }
    if (ok) scored.push({ e, score });
  }
  scored.sort((a, b) => b.score - a.score || b.e.d.localeCompare(a.e.d));
  return scored.slice(0, LIMIT).map((s) => s.e);
}

function prettyDate(iso: string): string {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function Highlight({ text, query }: { text: string; query: string }) {
  const words = fold(query).split(/\s+/).filter((w) => w.length > 1);
  if (!words.length) return <>{text}</>;
  const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return (
    <>
      {text.split(pattern).map((part, i) =>
        i % 2 === 1 ? <mark key={i}>{part}</mark> : <span key={i}>{part}</span>,
      )}
    </>
  );
}

export default function SearchPalette({
  open,
  onClose,
  latestDate,
}: {
  open: boolean;
  onClose: () => void;
  latestDate: string;
}) {
  const router = useRouter();
  const [index, setIndex] = useState<SearchEntry[] | null>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreFocus.current = document.activeElement as HTMLElement | null;
    loadIndex().then(setIndex);
    requestAnimationFrame(() => inputRef.current?.focus());
    document.documentElement.classList.add("no-scroll");
    return () => {
      document.documentElement.classList.remove("no-scroll");
      restoreFocus.current?.focus?.();
    };
  }, [open]);

  const results = useMemo(() => (index ? search(index, query) : []), [index, query]);

  useEffect(() => setActive(0), [query]);

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const go = useCallback(
    (e: SearchEntry) => {
      onClose();
      setQuery("");
      const base = e.d === latestDate ? "/" : `/archive/${e.d}/`;
      router.push(`${base}#item-${e.i}`);
    },
    [latestDate, onClose, router],
  );

  if (!open) return null;

  function onKeyDown(ev: React.KeyboardEvent) {
    if (ev.key === "Escape") {
      ev.preventDefault();
      onClose();
    } else if (ev.key === "ArrowDown") {
      ev.preventDefault();
      setActive((a) => Math.min(a + 1, Math.max(results.length - 1, 0)));
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (ev.key === "Enter" && results[active]) {
      ev.preventDefault();
      go(results[active]);
    } else if (ev.key === "Tab") {
      ev.preventDefault(); // keep focus inside the dialog
    }
  }

  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Search every edition"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="palette-input-row">
          <svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16">
            <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
            <path d="M10.5 10.5 14 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <input
            ref={inputRef}
            className="palette-input"
            placeholder="Search every edition — titles, sources, tags…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            role="combobox"
            aria-expanded={results.length > 0}
            aria-controls="palette-results"
            aria-activedescendant={results[active] ? `pr-${results[active].i}` : undefined}
            aria-autocomplete="list"
            spellCheck={false}
          />
          <kbd onClick={onClose}>esc</kbd>
        </div>
        <ul id="palette-results" ref={listRef} className="palette-results" role="listbox">
          {index === null && <li className="palette-empty">Loading the archive…</li>}
          {index !== null && !query && (
            <li className="palette-empty">
              {index.length.toLocaleString()} stories across every edition. Try “risc-v”, “benchmark”, or a repo name.
            </li>
          )}
          {index !== null && query && results.length === 0 && (
            <li className="palette-empty">Nothing matches “{query}”.</li>
          )}
          {results.map((e, i) => (
            <li
              key={e.i}
              id={`pr-${e.i}`}
              data-idx={i}
              role="option"
              aria-selected={i === active}
              className={i === active ? "palette-hit active" : "palette-hit"}
              onMouseMove={() => setActive(i)}
              onClick={() => go(e)}
            >
              <span className="palette-hit-title">
                <Highlight text={e.t} query={query} />
              </span>
              <span className="palette-hit-meta">
                <span>{prettyDate(e.d)}</span>
                <span>{e.c}</span>
                <span>{e.o}</span>
                {e.g && <span className="palette-tag">{e.g}</span>}
              </span>
            </li>
          ))}
        </ul>
        <div className="palette-foot">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> move
          </span>
          <span>
            <kbd>enter</kbd> open
          </span>
          <span>{results.length > 0 && `${results.length}${results.length === LIMIT ? "+" : ""} results`}</span>
        </div>
      </div>
    </div>
  );
}
