"""Nightly digest pipeline: fetch → dedupe → score → summarize → write.

Run manually:  python pipeline/main.py
Skip network fetch, reuse a fixture:  python pipeline/main.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))

import yaml

import output
from dedupe import SeenDB, dedupe
from fetchers import fetch_all
from scoring import Scorer
from summarize import summarize_all

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

logging.basicConfig(level=logging.INFO, format="%(name)-10s %(message)s")
log = logging.getLogger("main")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).parent / "config.yaml"))
    parser.add_argument("--no-summarize", action="store_true",
                        help="skip Gemini, use fallback summaries")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg.get("timezone", "UTC"))
    digest_date = datetime.now(tz).date().isoformat()
    lookback = datetime.now(timezone.utc) - timedelta(hours=cfg["lookback_hours"])

    log.info("digest date %s, lookback since %s", digest_date, lookback.isoformat())

    items, failed_sources = fetch_all(cfg["sources"], lookback)
    log.info("fetched %d items total (%d sources failed: %s)",
             len(items), len(failed_sources), ", ".join(failed_sources) or "none")

    db = SeenDB(str(DATA / "seen.sqlite"))
    fresh = dedupe(items, db, digest_date)
    buckets = Scorer(cfg).route_and_filter(fresh)

    if args.no_summarize:
        from summarize import _fallback
        for bucket in buckets.values():
            for it in bucket:
                it.summary = _fallback(it)
        used_gemini = False
    else:
        used_gemini = summarize_all(buckets, cfg["gemini"])

    kept = [it for b in buckets.values() for it in b]
    stats = {
        "fetched": len(items),
        "new_after_dedupe": len(fresh),
        "published": len(kept),
        "failed_sources": failed_sources,
        "summarizer": "gemini" if used_gemini else "fallback",
    }
    output.write(buckets, cfg, digest_date, stats, DATA)
    db.mark(kept, digest_date)

    retention = int(cfg.get("seen_retention_days", 90))
    cutoff = (datetime.now(tz).date() - timedelta(days=retention)).isoformat()
    pruned = db.prune(cutoff)
    log.info("published %d items, pruned %d old seen-rows", len(kept), pruned)

    # A night with zero published items is suspicious but not fatal;
    # exit 0 so the (unchanged) site keeps serving yesterday's digest.
    if not kept:
        log.warning("published 0 items — check failed sources above")
    return 0


if __name__ == "__main__":
    sys.exit(main())
