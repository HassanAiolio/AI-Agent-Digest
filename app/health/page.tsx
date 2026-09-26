import NightlyChart, { type Night } from "@/components/NightlyChart";
import { getAllDigests } from "@/lib/data";

export const metadata = {
  title: "Pipeline health",
  description: "How reliably the nightly pipeline has run: summaries, sources, faithfulness.",
};

function pct(n: number, d: number): string {
  return d ? `${Math.round((n / d) * 100)}%` : "—";
}

function short(iso: string): string {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export default function HealthPage() {
  const digests = getAllDigests(); // newest first
  const nights: Night[] = [...digests].reverse().map((d) => ({
    date: d.date,
    fetched: d.stats.fetched ?? 0,
    fresh: d.stats.new_after_dedupe ?? 0,
    published: d.stats.published ?? 0,
    llm: d.stats.summarizer !== "fallback",
    failed: d.stats.failed_sources ?? [],
    faithfulness: d.stats.faithfulness?.rate ?? null,
  }));

  const n = nights.length;
  const llmNights = nights.filter((x) => x.llm).length;
  const last30 = nights.slice(-30);
  const llm30 = last30.filter((x) => x.llm).length;
  const avg = (f: (x: Night) => number) => (n ? nights.reduce((s, x) => s + f(x), 0) / n : 0);

  // Faithfulness is pooled over claims, not averaged over nights, so a
  // night with 30 checked claims counts more than a night with 2.
  let checked = 0;
  let supported = 0;
  let dropped = 0;
  let trackedNights = 0;
  for (const d of digests) {
    const f = d.stats.faithfulness;
    if (!f) continue;
    trackedNights += 1;
    checked += f.checked;
    supported += f.supported;
    dropped += f.dropped;
  }

  const failures = new Map<string, { count: number; last: string }>();
  for (const x of nights) {
    for (const s of x.failed) {
      const prev = failures.get(s);
      failures.set(s, { count: (prev?.count ?? 0) + 1, last: x.date });
    }
  }
  const failureRows = [...failures.entries()].sort((a, b) => b[1].count - a[1].count);
  const cleanNights = nights.filter((x) => x.failed.length === 0).length;

  const funnel = [
    { label: "Fetched", value: avg((x) => x.fetched) },
    { label: "New after dedupe", value: avg((x) => x.fresh) },
    { label: "Published", value: avg((x) => x.published) },
  ];
  const funnelMax = Math.max(...funnel.map((f) => f.value), 1);

  return (
    <main className="page health">
      <header className="page-head">
        <p className="eyebrow-line">Pipeline health</p>
        <h1 className="page-title">How the robot is doing</h1>
        <p className="page-lede">
          Every edition records what the nightly run fetched, kept and summarized. This page is built from those
          records — {n} nights since {nights[0] ? short(nights[0].date) : "—"}.
        </p>
      </header>

      <div className="stat-grid">
        <div className="stat">
          <span className="stat-label">Editions shipped</span>
          <span className="stat-value">{n}</span>
          <span className="stat-note">{cleanNights} with every source up</span>
        </div>
        <div className="stat">
          <span className="stat-label">LLM-written nights</span>
          <span className="stat-value">{pct(llmNights, n)}</span>
          <span className="stat-note">
            {pct(llm30, last30.length)} over the last {last30.length}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Stories per night</span>
          <span className="stat-value">{avg((x) => x.published).toFixed(1)}</span>
          <span className="stat-note">from ~{Math.round(avg((x) => x.fetched))} fetched</span>
        </div>
        <div className="stat">
          <span className="stat-label">Numeric claims verified</span>
          <span className="stat-value">{checked ? pct(supported, checked) : "—"}</span>
          <span className="stat-note">
            {checked
              ? `${supported}/${checked} over ${trackedNights} night${trackedNights === 1 ? "" : "s"}, ${dropped} dropped`
              : "tracking starts with the next run"}
          </span>
        </div>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>Stories published per night</h2>
          <p>
            Bars in the warning color are nights where the LLM was unavailable and cards shipped raw abstracts. Hover
            or tap a bar for the night&rsquo;s numbers.
          </p>
        </div>
        <NightlyChart nights={nights} />
        <details className="table-toggle">
          <summary>Show as table</summary>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Night</th>
                  <th scope="col">Fetched</th>
                  <th scope="col">New</th>
                  <th scope="col">Published</th>
                  <th scope="col">Summaries</th>
                  <th scope="col">Sources down</th>
                </tr>
              </thead>
              <tbody>
                {[...nights].reverse().map((x) => (
                  <tr key={x.date}>
                    <td>{x.date}</td>
                    <td>{x.fetched}</td>
                    <td>{x.fresh}</td>
                    <td>{x.published}</td>
                    <td>{x.llm ? "LLM" : "raw abstracts"}</td>
                    <td>{x.failed.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      <div className="panel-row">
        <section className="panel">
          <div className="panel-head">
            <h2>Average night, as a funnel</h2>
            <p>Most of the work is throwing things away: repeats, then anything under the relevance bar.</p>
          </div>
          <div className="funnel">
            {funnel.map((f) => (
              <div key={f.label} className="funnel-row">
                <span className="funnel-label">{f.label}</span>
                <span className="funnel-track">
                  <span className="funnel-bar" style={{ width: `${(f.value / funnelMax) * 100}%` }} />
                </span>
                <span className="funnel-value">{f.value.toFixed(0)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Source failures</h2>
            <p>One source failing never stops the run; it just skips that source for the night.</p>
          </div>
          {failureRows.length === 0 ? (
            <p className="empty-inline">No source has failed yet.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Nights down</th>
                  <th scope="col">Last</th>
                </tr>
              </thead>
              <tbody>
                {failureRows.map(([name, f]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>
                      {f.count} <span className="muted">({pct(f.count, n)})</span>
                    </td>
                    <td>{short(f.last)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </main>
  );
}
