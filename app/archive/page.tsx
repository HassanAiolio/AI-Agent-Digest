import Link from "next/link";
import { type Digest, getAllDigests, getWeeklyIds } from "@/lib/data";

export const metadata = { title: "Archive" };

function lead(d: Digest): string {
  return d.brief?.stories[0]?.headline || d.highlights?.[0]?.title || d.sections[0]?.items[0]?.title || "—";
}

function monthLabel(key: string): string {
  return new Date(key + "-15T12:00:00Z").toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
}

function dayParts(iso: string) {
  const d = new Date(iso + "T12:00:00Z");
  return {
    num: d.getUTCDate(),
    weekday: d.toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" }),
  };
}

function isoWeek(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = Date.UTC(d.getUTCFullYear(), 0, 1);
  const week = Math.ceil(((d.getTime() - yearStart) / 86_400_000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

export default function ArchivePage() {
  const digests = getAllDigests();
  const weeklies = new Set(getWeeklyIds());
  const months = new Map<string, Digest[]>();
  for (const d of digests) {
    const key = d.date.slice(0, 7);
    if (!months.has(key)) months.set(key, []);
    months.get(key)!.push(d);
  }
  const stories = digests.reduce((n, d) => n + (d.stats.published ?? 0), 0);

  return (
    <main className="page">
      <header className="page-head">
        <p className="eyebrow-line">Archive</p>
        <h1 className="page-title">Every edition</h1>
        <p className="page-lede">
          {digests.length} editions and {stories.toLocaleString()} stories so far. Press <kbd>/</kbd> to search all of
          them.
        </p>
      </header>

      {digests.length === 0 && <p className="empty">No past editions yet.</p>}

      {[...months.entries()].map(([key, list]) => (
        <section key={key} className="archive-month">
          <h2 className="archive-month-title">{monthLabel(key)}</h2>
          <ol className="archive-list">
            {list.map((d) => {
              const { num, weekday } = dayParts(d.date);
              const week = isoWeek(d.date);
              const isSunday = weekday === "Sun";
              return (
                <li key={d.date}>
                  <Link href={`/archive/${d.date}/`} className="archive-row">
                    <span className="archive-day">
                      <span className="archive-num">{num}</span>
                      <span className="archive-weekday">{weekday}</span>
                    </span>
                    <span className="archive-lead">{lead(d)}</span>
                    <span className="archive-count">{d.stats.published ?? 0}</span>
                  </Link>
                  {isSunday && weeklies.has(week) && (
                    <Link href={`/weekly/${week}/`} className="archive-weekly">
                      Week in review · {week}
                    </Link>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </main>
  );
}
