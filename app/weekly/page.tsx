import Link from "next/link";
import { getWeekly, getWeeklyIds } from "@/lib/data";

export const metadata = { title: "Weekly" };

function range(start: string, end: string): string {
  const f = (iso: string) =>
    new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  return `${f(start)} – ${f(end)}`;
}

export default function WeeklyIndex() {
  const weeks = getWeeklyIds()
    .map((id) => getWeekly(id))
    .filter((w) => w !== null);
  return (
    <main className="page">
      <header className="page-head">
        <p className="eyebrow-line">Week in review</p>
        <h1 className="page-title">The weekly</h1>
        <p className="page-lede">
          Every Sunday, seven nights of signal boiled down to the few themes that kept coming back.
        </p>
      </header>
      {weeks.length === 0 ? (
        <p className="empty">The first recap lands on Sunday.</p>
      ) : (
        <ol className="weekly-list">
          {weeks.map((w) => (
            <li key={w.week}>
              <Link href={`/weekly/${w.week}/`} className="weekly-card">
                <span className="weekly-card-range">
                  {w.week} · {range(w.start, w.end)}
                </span>
                <span className="weekly-card-title">{w.title}</span>
                <span className="weekly-card-intro">{w.intro}</span>
                <span className="weekly-card-themes">{w.themes.map((t) => t.headline).join(" · ")}</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
