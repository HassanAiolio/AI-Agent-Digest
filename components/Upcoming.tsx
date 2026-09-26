"use client";
import { useEffect, useState } from "react";
import type { UpcomingEvent } from "@/lib/data";

function countdown(ms: number): string {
  if (ms <= 0) return "started";
  const mins = Math.floor(ms / 60_000);
  const d = Math.floor(mins / 1440);
  const h = Math.floor((mins % 1440) / 60);
  const m = mins % 60;
  if (d > 0) return `in ${d}d ${h}h`;
  if (h > 0) return `in ${h}h ${String(m).padStart(2, "0")}m`;
  return `in ${m}m`;
}

function utcLabel(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  return `${day} · ${time} UTC`;
}

function localLabel(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

function duration(detail: string): string {
  const m = detail.match(/(\d+(?:\.\d+)?)h/);
  return m ? `${m[1].replace(/\.0$/, "")}h` : "";
}

/** Contests starting soon, shown every night until they start. Times render
 * in UTC on the server and switch to the reader's local time (plus a live
 * countdown) after hydration, so there's no mismatch flash. */
export default function Upcoming({ events }: { events: UpcomingEvent[] }) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  const list = events.filter((e) => e.starts);
  if (!list.length) return null;

  return (
    <section className="upcoming" aria-labelledby="upcoming-title">
      <div className="upcoming-head">
        <h2 id="upcoming-title">On the clock</h2>
        <span>upcoming contests</span>
      </div>
      <ol className="upcoming-list">
        {list.map((e) => {
          const start = Date.parse(e.starts!);
          const soon = now !== null && start - now < 24 * 3_600_000 && start > now;
          return (
            <li key={e.id} className={soon ? "contest contest-soon" : "contest"}>
              <a href={e.url} target="_blank" rel="noopener noreferrer">
                <span className="contest-when">
                  {now === null ? utcLabel(e.starts!) : localLabel(e.starts!)}
                </span>
                <span className="contest-name">{e.title}</span>
                <span className="contest-meta">
                  <span>{e.source}</span>
                  {duration(e.detail) && <span>{duration(e.detail)}</span>}
                  {now !== null && <span className="contest-countdown">{countdown(start - now)}</span>}
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
