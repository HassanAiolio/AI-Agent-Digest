"""Deduplication in three layers:
1. Canonical URL identity (strips tracking params, normalizes arXiv/GitHub).
2. Seen-DB: an item published in a previous digest never reappears.
   Rows carry the digest date, so a re-run of the SAME night is idempotent —
   it rebuilds the same digest instead of producing an empty one.
3. In-run fuzzy title matching, so the arXiv paper and its HN thread merge.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

from models import Item, sha1

log = logging.getLogger("dedupe")

TRACKING = ("utm_", "ref", "ref_src", "fbclid", "gclid", "mc_cid", "mc_eid")
ARXIV_ID = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})")


def canonical_url(url: str) -> str:
    m = ARXIV_ID.search(url)
    if m:
        return f"https://arxiv.org/abs/{m.group(1)}"
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([
        (k, v) for k, v in parse_qsl(parts.query)
        if not any(k.lower().startswith(t) for t in TRACKING)
    ])
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


class SeenDB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            " id TEXT PRIMARY KEY, url TEXT, title TEXT, digest_date TEXT)"
        )
        self.conn.commit()

    def published_date(self, item_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT digest_date FROM seen WHERE id = ?", (item_id,)
        ).fetchone()
        return row[0] if row else None

    def mark(self, items: list[Item], digest_date: str) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO seen (id, url, title, digest_date) "
            "VALUES (?, ?, ?, ?)",
            [(it.id, it.url, it.title, digest_date) for it in items],
        )
        self.conn.commit()

    def prune(self, before_date: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM seen WHERE digest_date < ?", (before_date,)
        )
        self.conn.commit()
        return cur.rowcount


def dedupe(items: list[Item], db: SeenDB, digest_date: str) -> list[Item]:
    # Layer 1 + 2: canonical id, drop anything from an earlier digest.
    by_id: dict[str, Item] = {}
    dropped_seen = 0
    for it in items:
        it.id = sha1(canonical_url(it.url))
        prev = db.published_date(it.id)
        if prev is not None and prev != digest_date:
            dropped_seen += 1
            continue
        kept = by_id.get(it.id)
        if kept is None or _richness(it) > _richness(kept):
            by_id[it.id] = it

    # Layer 3: fuzzy titles across sources within this run.
    unique: list[Item] = []
    dropped_fuzzy = 0
    for it in sorted(by_id.values(), key=_richness, reverse=True):
        nt = norm_title(it.title)
        if any(fuzz.token_set_ratio(nt, norm_title(u.title)) >= 92 for u in unique):
            dropped_fuzzy += 1
            continue
        unique.append(it)

    log.info("dedupe: %d in, %d already published, %d fuzzy-merged, %d out",
             len(items), dropped_seen, dropped_fuzzy, len(unique))
    return unique


def _richness(it: Item) -> float:
    """Which duplicate to keep: prefer richer metadata and heavier sources."""
    return it.weight + (0.5 if it.abstract else 0) + (it.points or 0) / 1000.0
