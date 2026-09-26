"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Digest, DigestItem } from "@/lib/data";
import { useCollapsedSections } from "@/lib/collapsedSections";
import { useFeedback } from "@/lib/feedback";
import { useReadState } from "@/lib/readState";
import { useVisits } from "@/lib/visits";
import Brief from "./Brief";
import Freshness from "./Freshness";
import ItemRow from "./ItemRow";
import Upcoming from "./Upcoming";

export interface DigestViewProps {
  digest: Digest;
  isArchive?: boolean;
  edition: number;
  minutes: number;
  prev: string | null;
  next: string | null;
  latestDate: string;
  recentDates: string[]; // newest first
  weekly: { id: string; title: string } | null;
}

function longDate(iso: string): string {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function shortDate(iso: string): string {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

function personalize(items: DigestItem[], boost: (tag: string, source: string) => number): DigestItem[] {
  return [...items].sort((a, b) => b.score + boost(b.tag, b.source) - (a.score + boost(a.tag, a.source)));
}

const NAV_KEYS = new Set(["j", "k", "o", "enter"]);
const PICKS_ID = "top-picks";

export default function DigestView({
  digest,
  isArchive,
  edition,
  minutes,
  prev,
  next,
  latestDate,
  recentDates,
  weekly,
}: DigestViewProps) {
  const { stats } = digest;
  const failed = stats.failed_sources ?? [];
  const { castVote, getVote, boost } = useFeedback();
  const { isRead, markRead } = useReadState();
  const { collapsed, toggle: toggleSection, expand: expandSection } = useCollapsedSections();
  const visits = useVisits();

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [keyboardActive, setKeyboardActive] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [flashId, setFlashId] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const itemRefs = useRef<Record<string, HTMLElement | null>>({});

  const brief = digest.brief ?? null;
  // With a brief on top, a separate "top picks" list would repeat it; picks
  // are badged inside their sections instead. Older editions have no brief.
  const showPicks = !brief && (digest.highlights?.length ?? 0) > 0;

  const sections = useMemo(
    () => digest.sections.map((s) => ({ ...s, items: personalize(s.items, boost) })),
    [digest.sections, boost],
  );
  const picks = useMemo(
    () => (showPicks ? personalize(digest.highlights, boost) : []),
    [showPicks, digest.highlights, boost],
  );

  const itemsById = useMemo(() => {
    const map = new Map<string, DigestItem>();
    for (const s of sections) for (const i of s.items) map.set(i.id, i);
    return map;
  }, [sections]);

  const sectionOf = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of sections) for (const i of s.items) map.set(i.id, s.id);
    return map;
  }, [sections]);

  // Keyboard order: picks (when shown), then every expanded section.
  const flatIds = useMemo(() => {
    const ids: string[] = picks.map((i) => `pick-${i.id}`);
    for (const s of sections) {
      if (collapsed[s.id]) continue;
      ids.push(...s.items.map((i) => `item-${i.id}`));
    }
    return ids;
  }, [picks, sections, collapsed]);

  const toggleItem = useCallback(
    (id: string) => {
      setExpanded((prevState) => {
        const opening = !prevState[id];
        if (opening) markRead(id);
        return { ...prevState, [id]: opening };
      });
    },
    [markRead],
  );

  /** Open a card, unfold its section if needed, scroll it into view and
   * pulse it — used by the brief, deep links and search results. */
  const jumpTo = useCallback(
    (id: string, { updateHash = true } = {}) => {
      const sec = sectionOf.get(id);
      if (!sec) return;
      expandSection(sec);
      setExpanded((p) => ({ ...p, [id]: true }));
      markRead(id);
      setSelectedId(`item-${id}`);
      if (updateHash) window.history.replaceState(null, "", `#item-${id}`);
      // Wait a frame so an unfolding section has height before scrolling.
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          document.getElementById(`item-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
          setFlashId(id);
          setTimeout(() => setFlashId((f) => (f === id ? null : f)), 1600);
        }),
      );
    },
    [expandSection, markRead, sectionOf],
  );

  useEffect(() => {
    function fromHash() {
      const m = window.location.hash.match(/^#item-([0-9a-f]{40})$/);
      if (m) jumpTo(m[1], { updateHash: false });
    }
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, [jumpTo]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase();
      if (!NAV_KEYS.has(key) || flatIds.length === 0) return;
      // Enter on a focused button already activates it; only intercept when
      // the keyboard cursor is ours.
      if (key === "enter" && target?.tagName === "BUTTON") return;
      e.preventDefault();
      setKeyboardActive(true);

      if (key === "j" || key === "k") {
        setSelectedId((current) => {
          const idx = current ? flatIds.indexOf(current) : -1;
          const nextIdx = key === "j" ? Math.min(idx + 1, flatIds.length - 1) : Math.max(idx - 1, 0);
          const nextId = flatIds[Math.max(nextIdx, 0)];
          itemRefs.current[nextId]?.scrollIntoView({ block: "center", behavior: "smooth" });
          return nextId;
        });
      } else if (key === "enter" && selectedId) {
        toggleItem(selectedId.replace(/^(pick|item)-/, ""));
      } else if (key === "o" && selectedId) {
        const item = itemsById.get(selectedId.replace(/^(pick|item)-/, ""));
        if (item) window.open(item.url, "_blank", "noopener,noreferrer");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [flatIds, itemsById, selectedId, toggleItem]);

  // Scroll-spy for the section navigator.
  useEffect(() => {
    const els = [PICKS_ID, ...sections.map((s) => s.id)]
      .map((id) => document.getElementById(`sec-${id}`))
      .filter((el): el is HTMLElement => el !== null);
    if (!els.length) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveSection(visible[0].target.id.replace(/^sec-/, ""));
      },
      { rootMargin: "-120px 0px -55% 0px" },
    );
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, [sections]);

  const total = sections.reduce((n, s) => n + s.items.length, 0);
  const unread = (items: DigestItem[]) => items.filter((i) => !isRead(i.id)).length;
  const missed =
    !isArchive && visits?.previous
      ? recentDates.filter((d) => d > visits.previous! && d < latestDate)
      : [];

  function renderItem(item: DigestItem, anchorId: string, maxScore: number) {
    return (
      <ItemRow
        key={anchorId}
        ref={(el) => {
          itemRefs.current[anchorId] = el;
        }}
        anchorId={anchorId}
        item={item}
        maxScore={maxScore}
        vote={getVote(item.id)}
        onVote={(v) => castVote(item.id, item.tag, item.source, item.title, v)}
        open={Boolean(expanded[item.id])}
        onToggle={() => toggleItem(item.id)}
        read={isRead(item.id)}
        selected={keyboardActive && selectedId === anchorId}
        flash={flashId === item.id && anchorId.startsWith("item-")}
        latestDate={latestDate}
      />
    );
  }

  return (
    <main className="edition">
      <header className="hero">
        <div className="hero-meta">
          <span>No. {edition}</span>
          <span>{longDate(digest.date)}</span>
          <span>{minutes} min read</span>
        </div>
        {!brief && <h1 className="hero-title">{shortDate(digest.date)}</h1>}
        {isArchive && (
          <p className="archive-note">
            You&rsquo;re reading an archived edition.{" "}
            <Link href="/">Today&rsquo;s is here →</Link>
          </p>
        )}
        {missed.length > 1 && (
          <p className="welcome-back">
            Welcome back — you missed {missed.length} editions since {shortDate(visits!.previous!)}.{" "}
            <Link href={`/archive/${missed[missed.length - 1]}/`}>Start with the oldest →</Link>
          </p>
        )}
      </header>

      {brief && <Brief brief={brief} itemsById={itemsById} onJump={jumpTo} />}

      {digest.upcoming && digest.upcoming.length > 0 && !isArchive && <Upcoming events={digest.upcoming} />}

      {sections.length > 0 && (
        <nav className="section-nav" aria-label="Sections">
          <div className="section-nav-inner">
            {showPicks && (
              <a href={`#sec-${PICKS_ID}`} className={activeSection === PICKS_ID ? "active" : undefined}>
                Top picks
              </a>
            )}
            {sections.map((s) => {
              const u = unread(s.items);
              return (
                <a
                  key={s.id}
                  href={`#sec-${s.id}`}
                  className={activeSection === s.id ? "active" : undefined}
                  onClick={() => expandSection(s.id)}
                >
                  {s.title}
                  <span className="pill-count" aria-label={`${u} unread`}>
                    {u}
                  </span>
                </a>
              );
            })}
          </div>
        </nav>
      )}

      {digest.sections.length === 0 && <p className="empty">Nothing cleared the relevance bar tonight.</p>}

      {showPicks && (
        <section className="section" id={`sec-${PICKS_ID}`}>
          <div className="section-head">
            <h2>Top picks</h2>
            <span className="count">read these, skip the rest</span>
          </div>
          {picks.map((item) => renderItem(item, `pick-${item.id}`, Math.max(...picks.map((i) => i.score), 1)))}
        </section>
      )}

      {sections.map((section) => {
        const isCollapsed = Boolean(collapsed[section.id]);
        const maxScore = Math.max(...section.items.map((i) => i.score), 1);
        const u = unread(section.items);
        return (
          <section key={section.id} className="section" id={`sec-${section.id}`}>
            <div className="section-head">
              <button
                type="button"
                className="section-collapse"
                aria-expanded={!isCollapsed}
                aria-controls={`body-${section.id}`}
                onClick={() => toggleSection(section.id)}
              >
                <h2>{section.title}</h2>
                <svg className="chevron" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
                  <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <span className="count">
                {section.items.length} {section.items.length === 1 ? "story" : "stories"}
                {u > 0 && u < section.items.length && ` · ${u} unread`}
              </span>
            </div>
            <div id={`body-${section.id}`} className={isCollapsed ? "section-body collapsed" : "section-body"}>
              <div className="section-items">
                {section.items.map((item) => renderItem(item, `item-${item.id}`, maxScore))}
              </div>
            </div>
          </section>
        );
      })}

      {total > 0 && (
        <section className="caught-up" aria-label="End of edition">
          <div className="caught-up-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22">
              <path d="M5 12.5 10 17 19 7.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h2>You&rsquo;re all caught up.</h2>
          <p>
            {total} stories from {stats.fetched ?? "?"} scanned overnight
            {visits && visits.streak > 1 && !isArchive && (
              <>
                {" "}· day {visits.streak} of your reading streak
                {visits.best > visits.streak && ` (best ${visits.best})`}
              </>
            )}
            .
          </p>
          <div className="caught-up-links">
            {prev && (
              <Link href={`/archive/${prev}/`} className="cta">
                ← {shortDate(prev)}
              </Link>
            )}
            {weekly && (
              <Link href={`/weekly/${weekly.id}/`} className="cta cta-primary">
                This week: {weekly.title}
              </Link>
            )}
            {next && (
              <Link href={next === latestDate ? "/" : `/archive/${next}/`} className="cta">
                {shortDate(next)} →
              </Link>
            )}
          </div>
          <p className="subscribe">
            Get it every morning: <a href="/feed.xml">RSS feed</a>
            {process.env.NEXT_PUBLIC_NEWSLETTER_URL && (
              <>
                {" "}or <a href={process.env.NEXT_PUBLIC_NEWSLETTER_URL}>email</a>
              </>
            )}
            .
          </p>
        </section>
      )}

      <footer className="colophon">
        <span>
          {isArchive ? (
            "archived edition"
          ) : (
            <Freshness generatedAt={digest.generated_at} />
          )}
          {" · "}
          {stats.fetched ?? "?"} fetched → {stats.published ?? "?"} published
        </span>
        {stats.summarizer === "fallback" && <span className="degraded">summaries: raw abstracts (LLM unavailable)</span>}
        {failed.length > 0 && <span className="degraded">sources down: {failed.join(", ")}</span>}
        <span className="kbd-hint">
          <kbd>j</kbd>/<kbd>k</kbd> move · <kbd>enter</kbd> expand · <kbd>o</kbd> open · <kbd>/</kbd> search
        </span>
      </footer>
    </main>
  );
}
