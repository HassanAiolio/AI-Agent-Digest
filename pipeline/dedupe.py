"""Deduplication in three layers:
1. Canonical URL identity (strips tracking params, normalizes arXiv/GitHub).
2. Seen-DB: an item published in a previous digest never reappears
   (except evergreen items, like upcoming contests, which repeat until
   they happen).
   Rows carry the digest date, so a re-run of the SAME night is idempotent —
   it rebuilds the same digest instead of producing an empty one.
3. In-run fuzzy title matching, so the arXiv paper and its HN thread merge.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
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
    """Published-item ledger, stored as sorted JSON so the nightly commit is a
    readable text diff instead of a new copy of a binary SQLite file.

    Migrates transparently: if only the legacy seen.sqlite exists, its rows
    are imported on first open and the .sqlite file is deleted on save (the
    workflow's `git add data/` stages that removal).
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self.legacy = self.path.with_suffix(".sqlite")
        self.rows: dict[str, dict] = {}
        if self.path.exists():
            self.rows = json.loads(self.path.read_text(encoding="utf-8"))
        elif self.legacy.exists():
            conn = sqlite3.connect(self.legacy)
            try:
                for id_, url, title, date in conn.execute(
                        "SELECT id, url, title, digest_date FROM seen"):
                    self.rows[id_] = {"url": url, "title": title, "date": date}
            finally:
                conn.close()
            log.info("migrated %d rows from %s", len(self.rows), self.legacy.name)

    def published_date(self, item_id: str) -> str | None:
        row = self.rows.get(item_id)
        return row["date"] if row else None

    def mark(self, items: list[Item], digest_date: str) -> None:
        for it in items:
            self.rows[it.id] = {"url": it.url, "title": it.title, "date": digest_date}

    def prune(self, before_date: str) -> int:
        old = [k for k, v in self.rows.items() if v["date"] < before_date]
        for k in old:
            del self.rows[k]
        return len(old)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.rows, indent=0, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        if self.legacy.exists():
            self.legacy.unlink()


def dedupe(items: list[Item], db: SeenDB, digest_date: str) -> list[Item]:
    # Layer 1 + 2: canonical id, drop anything from an earlier digest.
    by_id: dict[str, Item] = {}
    dropped_seen = 0
    for it in items:
        it.id = sha1(canonical_url(it.url))
        prev = db.published_date(it.id)
        if prev is not None and prev != digest_date and not it.evergreen:
            dropped_seen += 1
            continue
        kept = by_id.get(it.id)
        if kept is None or _richness(it) > _richness(kept):
            by_id[it.id] = it

    # Layer 3: fuzzy titles across sources within this run.
    unique: list[Item] = []
    dropped_fuzzy = 0
    for it in sorted(by_id.values(), key=_richness, reverse=True):
        if it.evergreen:
            # "Codeforces Round 1050 (Div. 2)" and "... 1051 (Div. 2)" score
            # ~96 on token_set_ratio but are different contests; their URL
            # identity from layer 1 is already exact.
            unique.append(it)
            continue
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
