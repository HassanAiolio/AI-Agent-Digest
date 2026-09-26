import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLatestDigest, getWeekly, getWeeklyIds, type WeeklyRef } from "@/lib/data";
import { Inline } from "@/lib/inline";

export function generateStaticParams() {
  return getWeeklyIds().map((week) => ({ week }));
}

export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ week: string }> }): Promise<Metadata> {
  const { week } = await params;
  const w = getWeekly(week);
  return { title: w ? `${w.title} (${week})` : week, description: w?.intro };
}

function short(iso: string): string {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

function href(ref: WeeklyRef, latest: string): string {
  return ref.date === latest ? `/#item-${ref.id}` : `/archive/${ref.date}/#item-${ref.id}`;
}

export default async function WeeklyPage({ params }: { params: Promise<{ week: string }> }) {
  const { week } = await params;
  const w = getWeekly(week);
  if (!w) notFound();
  const latest = getLatestDigest().date;
  const ids = getWeeklyIds();
  const idx = ids.indexOf(week);
  const older = ids[idx + 1];
  const newer = idx > 0 ? ids[idx - 1] : undefined;

  return (
    <main className="page weekly">
      <header className="page-head">
        <p className="eyebrow-line">
          Week in review · {short(w.start)} – {short(w.end)} · {w.item_count} stories read
        </p>
        <h1 className="page-title">{w.title}</h1>
        <p className="brief-lede">{w.intro}</p>
      </header>

      {w.numbers.length > 0 && (
        <div className="weekly-numbers">
          {w.numbers.map((n, i) => (
            <Link key={i} href={href(n.item, latest)} className="number-card">
              <span className="number-eyebrow">By the numbers</span>
              <span className={n.value.length > 5 ? "number-value number-value-long" : "number-value"}>{n.value}</span>
              <span className="number-label">{n.label}</span>
            </Link>
          ))}
        </div>
      )}

      <div className="brief-stories">
        {w.themes.map((t, i) => (
          <article key={i} className="story">
            <div className="story-rail" aria-hidden="true">
              {String(i + 1).padStart(2, "0")}
            </div>
            <div className="story-main">
              <h2 className="story-headline">{t.headline}</h2>
              <p className="story-body">
                <Inline text={t.body} />
              </p>
              <ul className="theme-refs">
                {t.items.map((ref) => (
                  <li key={ref.id}>
                    <Link href={href(ref, latest)}>{ref.title}</Link>
                    <span>
                      {short(ref.date)} · {ref.source}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </article>
        ))}
      </div>

      {w.watch && (
        <p className="story-why weekly-watch">
          <span className="story-why-label">Watch next week</span>
          {w.watch}
        </p>
      )}

      <div className="caught-up-links weekly-nav">
        {older && (
          <Link href={`/weekly/${older}/`} className="cta">
            ← {older}
          </Link>
        )}
        <Link href="/" className="cta cta-primary">
          Today&rsquo;s edition
        </Link>
        {newer && (
          <Link href={`/weekly/${newer}/`} className="cta">
            {newer} →
          </Link>
        )}
      </div>
    </main>
  );
}
