import type { Digest, DigestItem } from "@/lib/data";
import Freshness from "./Freshness";

function displayDate(iso: string): string {
  const d = new Date(iso + "T12:00:00Z");
  return d
    .toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
    .toUpperCase();
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function ItemRow({ item, maxScore }: { item: DigestItem; maxScore: number }) {
  const pct = Math.max(8, Math.round((item.score / maxScore) * 100));
  return (
    <article className="item">
      <h3>
        <a href={item.url} target="_blank" rel="noopener noreferrer">
          {item.title}
        </a>
      </h3>
      <div className="meta">
        <span className="signal" title={`relevance ${item.score}`} aria-hidden="true">
          <span style={{ width: `${pct}%` }} />
        </span>
        <span>{item.source}</span>
        <span>{host(item.url)}</span>
        {item.points != null && <span>{item.points.toLocaleString()} pts</span>}
        {item.published && <span>{item.published.slice(0, 10)}</span>}
      </div>
      {item.summary && <p className="summary">{item.summary}</p>}
    </article>
  );
}

export default function DigestView({ digest, isArchive }: { digest: Digest; isArchive?: boolean }) {
  const { stats } = digest;
  const failed = stats.failed_sources ?? [];
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
            <span className="degraded">summaries: raw abstracts (Gemini unavailable)</span>
          )}
          {failed.length > 0 && (
            <span className="degraded">sources down: {failed.join(", ")}</span>
          )}
        </div>
      </header>

      {digest.sections.length === 0 && (
        <p className="empty">Nothing cleared the relevance bar tonight.</p>
      )}

      {digest.sections.map((section) => {
        const maxScore = Math.max(...section.items.map((i) => i.score), 1);
        return (
          <section key={section.id} className="section">
            <div className="section-head">
              <span className="tier">T{section.tier}</span>
              <h2>{section.title}</h2>
              <span className="count">{section.items.length} items</span>
            </div>
            {section.items.map((item) => (
              <ItemRow key={item.id} item={item} maxScore={maxScore} />
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
