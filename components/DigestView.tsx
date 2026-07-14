"use client";
import { useMemo } from "react";
import type { Digest, DigestItem } from "@/lib/data";
import { useFeedback } from "@/lib/feedback";
import Freshness from "./Freshness";
import ItemRow from "./ItemRow";

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

export default function DigestView({ digest, isArchive }: { digest: Digest; isArchive?: boolean }) {
  const { stats } = digest;
  const failed = stats.failed_sources ?? [];
  const { castVote, getVote, boost } = useFeedback();

  const highlights = useMemo(
    () => personalize(digest.highlights ?? [], boost),
    [digest.highlights, boost],
  );
  const sections = useMemo(
    () => digest.sections.map((s) => ({ ...s, items: personalize(s.items, boost) })),
    [digest.sections, boost],
  );

  return (
    <main>
      <header className="masthead">
        <div className="eyebrow">
          <span>Nightly digest · AI + CS signal</span>
          <nav>
            <a href="/">Tonight</a>
            <a href="/archive/">Archive</a>
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
      </header>

      {digest.sections.length === 0 && (
        <p className="empty">Nothing cleared the relevance bar tonight.</p>
      )}

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
                item={item}
                maxScore={Math.max(...highlights.map((it) => it.score), 1)}
                emphasized
                vote={getVote(item.id)}
                onVote={(v) => castVote(item.id, item.tag, item.source, v)}
              />
            </div>
          ))}
        </section>
      )}

      {sections.map((section) => {
        const maxScore = Math.max(...section.items.map((i) => i.score), 1);
        return (
          <section key={section.id} className="section">
            <div className="section-head">
              <span className="tier">T{section.tier}</span>
              <h2>{section.title}</h2>
              <span className="count">{section.items.length} items</span>
            </div>
            {section.items.map((item, i) => (
              <div key={item.id} className="item-enter" style={{ animationDelay: `${Math.min(i, 8) * 35}ms` }}>
                <ItemRow
                  item={item}
                  maxScore={maxScore}
                  vote={getVote(item.id)}
                  onVote={(v) => castVote(item.id, item.tag, item.source, v)}
                />
              </div>
            ))}
          </section>
        );
      })}

      <footer className="colophon">
        <span>fetch → dedupe → score → summarize, nightly via GitHub Actions</span>
        <a href="/archive/">past editions →</a>
      </footer>
    </main>
  );
}
