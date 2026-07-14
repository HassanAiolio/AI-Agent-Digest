import { getArchiveDates } from "@/lib/data";

export const metadata = { title: "Archive · Nightly digest" };

export default function ArchivePage() {
  const dates = getArchiveDates();
  return (
    <main>
      <header className="masthead">
        <div className="eyebrow">
          <span>Nightly digest · archive</span>
          <nav>
            <a href="/">Tonight</a>
          </nav>
        </div>
        <h1>Archive</h1>
      </header>
      {dates.length === 0 ? (
        <p className="empty">No past editions yet.</p>
      ) : (
        <ul className="archive-list">
          {dates.map((d) => (
            <li key={d}>
              <a href={`/archive/${d}/`}>
                <span>{d}</span>
                <span>→</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
