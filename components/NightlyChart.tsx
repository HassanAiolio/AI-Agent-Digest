"use client";
import { useMemo, useRef, useState } from "react";

export interface Night {
  date: string;
  fetched: number;
  fresh: number;
  published: number;
  llm: boolean;
  failed: string[];
  faithfulness: number | null;
}

const H = 180; // plot height
const PAD_L = 28;
const PAD_B = 22;
const GAP = 2; // surface gap between adjacent bars

function niceMax(v: number): number {
  const step = v <= 20 ? 5 : v <= 50 ? 10 : 20;
  return Math.max(step, Math.ceil(v / step) * step);
}

function short(iso: string): string {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/** One bar per night, height = stories published. Single series in the
 * accent color; fallback nights take the reserved warning color and are
 * also marked with a small triangle above the bar, so the state is never
 * carried by color alone. */
export default function NightlyChart({ nights }: { nights: Night[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const W = 720;
  const max = useMemo(() => niceMax(Math.max(...nights.map((n) => n.published), 1)), [nights]);
  const plotW = W - PAD_L;
  const slot = nights.length ? plotW / nights.length : plotW;
  const barW = Math.max(1, slot - GAP);
  const y = (v: number) => H - (v / max) * H;
  const ticks = [0, max / 2, max];

  // Month labels at the first night of each month.
  const monthTicks = nights
    .map((n, i) => ({ i, n }))
    .filter(({ n, i }) => i === 0 || n.date.slice(0, 7) !== nights[i - 1].date.slice(0, 7));

  const h = hover !== null ? nights[hover] : null;
  const tipLeft = hover !== null ? ((PAD_L + hover * slot + slot / 2) / W) * 100 : 0;

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W - PAD_L;
    const i = Math.floor(x / slot);
    setHover(i >= 0 && i < nights.length ? i : null);
  }

  if (!nights.length) return <p className="empty-inline">No nights recorded yet.</p>;

  return (
    <div className="chart" ref={wrapRef}>
      <div className="chart-legend" aria-hidden="true">
        <span>
          <i className="swatch swatch-ok" /> LLM summaries
        </span>
        <span>
          <i className="swatch swatch-warn" /> ▲ raw-abstract fallback
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H + PAD_B + 12}`}
        className="chart-svg"
        role="img"
        aria-label={`Stories published per night over ${nights.length} nights, between ${nights[0].date} and ${nights[nights.length - 1].date}.`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <g transform="translate(0, 12)">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD_L} x2={W} y1={y(t)} y2={y(t)} className="grid" />
              <text x={PAD_L - 6} y={y(t)} className="axis-label" textAnchor="end" dominantBaseline="middle">
                {t}
              </text>
            </g>
          ))}
          {nights.map((n, i) => {
            const x = PAD_L + i * slot + GAP / 2;
            const top = y(n.published);
            const hgt = Math.max(H - top, n.published ? 2 : 0);
            const r = Math.min(4, barW / 2, hgt);
            // Rounded data-end (top), square at the baseline.
            const d = `M${x},${H} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${H} Z`;
            return (
              <g key={n.date} className={hover === i ? "bar-group hovered" : "bar-group"}>
                {hgt > 0 && <path d={d} className={n.llm ? "bar bar-ok" : "bar bar-warn"} />}
                {!n.llm && (
                  <path
                    d={`M${x + barW / 2 - 3},${top - 4} h6 l-3,-5 z`}
                    className="bar-marker"
                  />
                )}
              </g>
            );
          })}
          {monthTicks.map(({ i, n }) => (
            <text key={n.date} x={PAD_L + i * slot} y={H + 16} className="axis-label">
              {new Date(n.date + "T12:00:00Z").toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" })}
            </text>
          ))}
          {hover !== null && (
            <line
              x1={PAD_L + hover * slot + slot / 2}
              x2={PAD_L + hover * slot + slot / 2}
              y1={0}
              y2={H}
              className="crosshair"
            />
          )}
        </g>
      </svg>
      {h && (
        <div className="tooltip" style={{ left: `clamp(80px, ${tipLeft}%, calc(100% - 80px))` }} role="status">
          <strong>{short(h.date)}</strong>
          <span>
            {h.published} published <span className="muted">of {h.fetched} fetched</span>
          </span>
          <span>{h.llm ? "LLM summaries" : "▲ raw-abstract fallback"}</span>
          {h.failed.length > 0 && <span className="muted">down: {h.failed.join(", ")}</span>}
          {h.faithfulness !== null && <span>{Math.round(h.faithfulness * 100)}% claims verified</span>}
        </div>
      )}
    </div>
  );
}
