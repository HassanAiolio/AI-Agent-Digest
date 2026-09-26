"use client";
import Image from "next/image";
import Link from "next/link";
import { forwardRef, useState, type MouseEvent } from "react";
import type { DigestItem } from "@/lib/data";

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

const PROXIED = new Set((process.env.NEXT_PUBLIC_IMAGE_HOSTS ?? "").split(",").filter(Boolean));

/** "proxied" → next/image; "direct" → plain <img>; null → no thumbnail
 * (relative or non-https URLs from older editions). */
function imageMode(src: string): "proxied" | "direct" | null {
  try {
    const u = new URL(src);
    if (u.protocol !== "https:") return null;
    return PROXIED.has(u.hostname) ? "proxied" : "direct";
  } catch {
    return null;
  }
}

/** HN points, GitHub stars and HF likes all arrive as item.points. */
function pointsUnit(source: string): string {
  if (source.startsWith("GitHub")) return "★";
  if (source.startsWith("HF")) return "likes";
  return "pts";
}

function shortDate(iso: string): string {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

interface ItemRowProps {
  item: DigestItem;
  anchorId: string;
  maxScore: number;
  vote?: 1 | -1;
  onVote: (value: 1 | -1) => void;
  open: boolean;
  onToggle: () => void;
  read?: boolean;
  selected?: boolean;
  flash?: boolean;
  latestDate: string;
}

const ItemRow = forwardRef<HTMLElement, ItemRowProps>(function ItemRow(
  { item, anchorId, maxScore, vote, onVote, open, onToggle, read, selected, flash, latestDate },
  ref,
) {
  const [imgBroken, setImgBroken] = useState(false);
  const [copied, setCopied] = useState(false);
  const pct = Math.max(8, Math.round((item.score / maxScore) * 100));
  const mode = item.image ? imageMode(item.image) : null;
  const showImage = mode !== null && !imgBroken;
  const related = item.related && "url" in item.related ? item.related : null;
  const detailId = `${anchorId}-detail`;

  function copyLink(e: MouseEvent) {
    e.stopPropagation();
    const url = `${window.location.origin}${window.location.pathname}#${anchorId}`;
    navigator.clipboard
      .writeText(url)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {
        /* clipboard unavailable — no-op */
      });
  }

  const relatedHref = related
    ? related.date === latestDate
      ? `/#item-${related.id}`
      : `/archive/${related.date}/#item-${related.id}`
    : "";

  return (
    <article
      ref={ref}
      id={anchorId}
      className={[
        "item",
        open && "item-open",
        read && "item-read",
        selected && "item-selected",
        flash && "item-flash",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className={showImage ? "item-body with-image" : "item-body"}>
        <div className="item-content">
          <div className="meta meta-top">
            {item.highlight && <span className="pick">Top pick</span>}
            {item.tag && <span className="tag">{item.tag}</span>}
            <span className="meta-source">{item.source}</span>
            {item.points != null && <span>{item.points.toLocaleString()} {pointsUnit(item.source)}</span>}
            <span className="signal" title={`relevance ${item.score}`} aria-hidden="true">
              <span style={{ width: `${pct}%` }} />
            </span>
          </div>
          <h3 className="item-title">
            <button type="button" aria-expanded={open} aria-controls={detailId} onClick={onToggle}>
              <span>{item.title}</span>
              <span className="chevron" aria-hidden="true">
                <svg viewBox="0 0 12 12" width="12" height="12">
                  <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </button>
          </h3>
          {item.summary && <p className="summary">{item.summary}</p>}
          {item.key_points.length > 0 && (
            <ul className="key-points" aria-label="Key facts">
              {item.key_points.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
          <div id={detailId} className={open ? "detail detail-open" : "detail"}>
            <div className="detail-inner">
              {item.detail && item.detail !== item.summary && <p className="detail-text">{item.detail}</p>}
              {related && (
                <p className="related">
                  <span className="related-label">Previously in the digest</span>
                  <Link href={relatedHref}>{related.title}</Link>
                  <span className="related-date">{shortDate(related.date)}</span>
                </p>
              )}
            </div>
          </div>
          <div className="item-actions">
            <a className="read-source" href={item.url} target="_blank" rel="noopener noreferrer">
              {host(item.url) || "Read source"} <span aria-hidden="true">↗</span>
            </a>
            <button type="button" className="ghost-btn" onClick={copyLink}>
              {copied ? "Copied" : "Copy link"}
            </button>
            <span className="votes">
              <button
                type="button"
                className="vote-btn vote-up"
                aria-pressed={vote === 1}
                aria-label="More like this"
                title="More like this"
                onClick={(e) => {
                  e.stopPropagation();
                  onVote(1);
                }}
              >
                <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
                  <path d="M6 2.5 10 8H2z" fill="currentColor" />
                </svg>
              </button>
              <button
                type="button"
                className="vote-btn vote-down"
                aria-pressed={vote === -1}
                aria-label="Less like this"
                title="Less like this"
                onClick={(e) => {
                  e.stopPropagation();
                  onVote(-1);
                }}
              >
                <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
                  <path d="M6 9.5 2 4h8z" fill="currentColor" />
                </svg>
              </button>
            </span>
          </div>
        </div>
        {showImage &&
          (mode === "proxied" ? (
            <Image
              src={item.image}
              alt=""
              className="item-thumb"
              width={224}
              height={140}
              sizes="112px"
              onError={() => setImgBroken(true)}
            />
          ) : (
            // Host outside the next/image allowlist: load directly, but
            // without leaking the page URL as referrer.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.image}
              alt=""
              className="item-thumb"
              width={112}
              height={70}
              loading="lazy"
              decoding="async"
              referrerPolicy="no-referrer"
              onError={() => setImgBroken(true)}
            />
          ))}
      </div>
    </article>
  );
});

export default ItemRow;
