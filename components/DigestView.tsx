"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Digest, DigestItem } from "@/lib/data";
import { useCollapsedSections } from "@/lib/collapsedSections";
import { useFeedback } from "@/lib/feedback";
import { useReadState } from "@/lib/readState";
import Freshness from "./Freshness";
import ItemRow from "./ItemRow";
import ThemeToggle from "./ThemeToggle";

function displayDate(iso: string): string {
  const d = new Date(iso + "T12:00:00Z");
  return d
    .toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
    .toUpperCase();
}

function personalize(items: DigestItem[], boost: (tag: string, source: string) => number): DigestItem[] {
  return [...items].sort(
    (a, b) => b.score + boost(b.tag, b.source) - (a.score + boost(a.tag, a.source)),
  );
}

function matches(item: DigestItem, q: string): boolean {
  const hay = `${item.title} ${item.source} ${item.tag} ${item.summary}`.toLowerCase();
  return hay.includes(q);
}

const NAV_KEYS = new Set(["j", "k", "o", "enter"]);

export default function DigestView({ digest, isArchive }: { digest: Digest; isArchive?: boolean }) {
  const { stats } = digest;
  const failed = stats.failed_sources ?? [];
  const { castVote, getVote, boost } = useFeedback();
  const { isRead, markRead } = useReadState();
  const { collapsed, toggle: toggleSection } = useCollapsedSections();

  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [keyboardActive, setKeyboardActive] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const itemRefs = useRef<Record<string, HTMLElement | null>>({});

  const toggleItem = useCallback(
    (id: string) => {
      setExpanded((prev) => {
        const opening = !prev[id];
        if (opening) markRead(id);
        return { ...prev, [id]: opening };
      });
    },
    [markRead],
  );

  const q = query.trim().toLowerCase();

  const highlights = useMemo(() => {
    const list = personalize(digest.highlights ?? [], boost);
    return q ? list.filter((i) => matches(i, q)) : list;
  }, [digest.highlights, boost, q]);

  const sections = useMemo(() => {
    return digest.sections
      .map((s) => ({ ...s, items: personalize(s.items, boost).filter((i) => (q ? matches(i, q) : true)) }))
      .filter((s) => s.items.length > 0 || !q);
  }, [digest.sections, boost, q]);

  const flatIds = useMemo(() => {
    const ids: string[] = highlights.map((i) => i.id);
    for (const s of sections) {
      if (collapsed[s.id]) continue;
      ids.push(...s.items.map((i) => i.id));
    }
    return ids;
  }, [highlights, sections, collapsed]);

  const itemsById = useMemo(() => {
    const map = new Map<string, DigestItem>();
    for (const i of highlights) map.set(i.id, i);
    for (const s of sections) for (const i of s.items) map.set(i.id, i);
    return map;
  }, [highlights, sections]);

  const totalMatches = flatIds.length;

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable) return;
      const key = e.key.toLowerCase();
      if (!NAV_KEYS.has(key)) return;
      if (flatIds.length === 0) return;
      e.preventDefault();
      setKeyboardActive(true);

      if (key === "j" || key === "k") {
        setSelectedId((current) => {
          const idx = current ? flatIds.indexOf(current) : -1;
          const nextIdx = key === "j" ? Math.min(idx + 1, flatIds.length - 1) : Math.max(idx - 1, 0);
          const nextId = flatIds[Math.max(nextIdx, 0)];
          itemRefs.current[nextId]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
          return nextId;
        });
      } else if (key === "enter") {
        if (selectedId) toggleItem(selectedId);
      } else if (key === "o") {
        const item = selectedId ? itemsById.get(selectedId) : undefined;
        if (item) window.open(item.url, "_blank", "noopener,noreferrer");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [flatIds, itemsById, selectedId, toggleItem]);

  return (
    <main>
      <header className="masthead">
        <div className="eyebrow">
          <span>Nightly digest · AI + CS signal</span>
          <nav>
            <a href="/">Tonight</a>
            <a href="/archive/">Archive</a>
            <ThemeToggle />
          </nav>
        </div>
        <h1>{displayDate(digest.date)}</h1>
        <div className="runline">
          {isArchive ? (
            <span>archived edition</span>
          ) : (
            <Freshness generatedAt={digest.generated_at} />
          )}
          <span>
            {stats.fetched ?? "?"} fetched → {stats.published ?? "?"} published
          </span>
          {stats.summarizer === "fallback" && (
            <span className="degraded">summaries: raw abstracts (Groq unavailable)</span>
          )}
          {failed.length > 0 && (
            <span className="degraded">sources down: {failed.join(", ")}</span>
          )}
        </div>
        <div className="search-row">
          <input
            type="search"
            className="search-input"
            placeholder="Filter by title, source, or tag…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Filter items"
          />
          {q && (
            <span className="search-count">
              {totalMatches} match{totalMatches === 1 ? "" : "es"}
            </span>
          )}
        </div>
      </header>

      {digest.sections.length === 0 && (
        <p className="empty">Nothing cleared the relevance bar tonight.</p>
      )}
      {q && totalMatches === 0 && <p className="empty">No items match “{query}”.</p>}

      {highlights.length > 0 && (
        <section className="section highlights">
          <div className="section-head">
            <span className="tier">★</span>
            <h2>Tonight&rsquo;s top picks</h2>
            <span className="count">read these, skip the rest</span>
          </div>
          {highlights.map((item, i) => (
            <div key={item.id} className="item-enter" style={{ animationDelay: `${Math.min(i, 8) * 35}ms` }}>
              <ItemRow
                ref={(el) => {
                  itemRefs.current[item.id] = el;
                }}
                item={item}
                maxScore={Math.max(...highlights.map((it) => it.score), 1)}
                emphasized
                vote={getVote(item.id)}
                onVote={(v) => castVote(item.id, item.tag, item.source, v)}
                open={Boolean(expanded[item.id])}
                onToggle={() => toggleItem(item.id)}
                read={isRead(item.id)}
                selected={keyboardActive && selectedId === item.id}
              />
            </div>
          ))}
        </section>
      )}

      {sections.map((section) => {
        const isCollapsed = Boolean(collapsed[section.id]);
        const maxScore = Math.max(...section.items.map((i) => i.score), 1);
        return (
          <section key={section.id} className="section">
            <div className="section-head">
              <button
                type="button"
                className="section-collapse"
                aria-expanded={!isCollapsed}
                onClick={() => toggleSection(section.id)}
              >
                <span className="chevron" aria-hidden="true">▸</span>
                <span className="tier">T{section.tier}</span>
                <h2>{section.title}</h2>
              </button>
              <span className="count">{section.items.length} items</span>
            </div>
            <div className={isCollapsed ? "section-body collapsed" : "section-body"}>
              <div className="section-items">
                {section.items.map((item, i) => (
                  <div key={item.id} className="item-enter" style={{ animationDelay: `${Math.min(i, 8) * 35}ms` }}>
                    <ItemRow
                      ref={(el) => {
                        itemRefs.current[item.id] = el;
                      }}
                      item={item}
                      maxScore={maxScore}
                      vote={getVote(item.id)}
                      onVote={(v) => castVote(item.id, item.tag, item.source, v)}
                      open={Boolean(expanded[item.id])}
                      onToggle={() => toggleItem(item.id)}
                      read={isRead(item.id)}
                      selected={keyboardActive && selectedId === item.id}
                    />
                  </div>
                ))}
              </div>
            </div>
          </section>
        );
      })}

      <footer className="colophon">
        <span>fetch → dedupe → score → summarize, nightly via GitHub Actions</span>
        <span className="kbd-hint">j/k navigate · enter expands · o opens source</span>
        <a href="/archive/">past editions →</a>
      </footer>
    </main>
  );
}
