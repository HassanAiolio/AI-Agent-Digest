"use client";
import { useState } from "react";
import type { DigestItem } from "@/lib/data";

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export default function ItemRow({
  item,
  maxScore,
  emphasized,
  vote,
  onVote,
}: {
  item: DigestItem;
  maxScore: number;
  emphasized?: boolean;
  vote?: 1 | -1;
  onVote: (value: 1 | -1) => void;
}) {
  const [open, setOpen] = useState(false);
  const pct = Math.max(8, Math.round((item.score / maxScore) * 100));

  return (
    <article className={["item", emphasized && "item-highlight", open && "item-open"].filter(Boolean).join(" ")}>
      <h3 className="item-title">
        <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span className="chevron" aria-hidden="true">▸</span>
          {item.title}
        </button>
      </h3>
      <div className="meta">
        <span className="signal" title={`relevance ${item.score}`} aria-hidden="true">
          <span style={{ width: `${pct}%` }} />
        </span>
        {item.tag && <span className="tag">{item.tag}</span>}
        <span>{item.source}</span>
        <span>{host(item.url)}</span>
        {item.points != null && <span>{item.points.toLocaleString()} pts</span>}
        {item.published && <span>{item.published.slice(0, 10)}</span>}
        <span className="votes">
          <button
            type="button"
            className="vote-btn vote-up"
            aria-pressed={vote === 1}
            aria-label="Like — see more like this"
            onClick={(e) => {
              e.stopPropagation();
              onVote(1);
            }}
          >
            ▲
          </button>
          <button
            type="button"
            className="vote-btn vote-down"
            aria-pressed={vote === -1}
            aria-label="Dislike — see less like this"
            onClick={(e) => {
              e.stopPropagation();
              onVote(-1);
            }}
          >
            ▼
          </button>
        </span>
      </div>
      {item.summary && <p className="summary">{item.summary}</p>}
      {item.key_points.length > 0 && (
        <ul className="key-points">
          {item.key_points.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      )}
      <div className={open ? "detail detail-open" : "detail"}>
        <div className="detail-inner">
          {item.detail ? (
            <p className="detail-text">{item.detail}</p>
          ) : (
            item.summary && <p className="detail-text">{item.summary}</p>
          )}
          <a className="read-source" href={item.url} target="_blank" rel="noopener noreferrer">
            Read source ↗
          </a>
        </div>
      </div>
    </article>
  );
}
