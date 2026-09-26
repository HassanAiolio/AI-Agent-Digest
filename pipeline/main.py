"""Nightly digest pipeline:
fetch → dedupe → score → thumbnails → summarize → verify → relate → personalize
→ brief → write (→ weekly recap on Sundays).

Run manually:  python pipeline/main.py
Skip the LLM, use fallback summaries:  python pipeline/main.py --no-summarize
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))

import yaml

import brief as brief_mod
import images
import output
import preferences
import semantic
import verify
import weekly
from dedupe import SeenDB, _richness, dedupe
from fetchers import fetch_all
from scoring import Scorer
from summarize import _fallback, _fallback_detail, summarize_all

ROOT = Path(__file__).resolve().parent.parent
DATA_DEFAULT = ROOT / "data"

logging.basicConfig(level=logging.INFO, format="%(name)-10s %(message)s")
log = logging.getLogger("main")


def _report(outputs: dict[str, str]) -> None:
    """Expose run health to later workflow steps (alerting) via
    $GITHUB_OUTPUT. A no-op outside GitHub Actions."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for k, v in outputs.items():
            f.write(f"{k}={v}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).parent / "config.yaml"))
    parser.add_argument("--no-summarize", action="store_true",
                        help="skip the LLM, use fallback summaries")
    parser.add_argument("--weekly", action="store_true",
                        help="also build the weekly recap regardless of weekday")
    parser.add_argument("--data-dir", default=str(DATA_DEFAULT),
                        help="where digest/archive/seen/feedback live (default: repo data/)")
    args = parser.parse_args()
    data = Path(args.data_dir)

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg.get("timezone", "UTC"))
    digest_date = datetime.now(tz).date().isoformat()
    lookback = datetime.now(timezone.utc) - timedelta(hours=cfg["lookback_hours"])
    scfg = cfg.get("semantic", {})
    use_semantic = scfg.get("enabled", True)

    log.info("digest date %s, lookback since %s", digest_date, lookback.isoformat())

    items, failed_sources = fetch_all(cfg["sources"], lookback)
    log.info("fetched %d items total (%d sources failed: %s)",
             len(items), len(failed_sources), ", ".join(failed_sources) or "none")

    db = SeenDB(str(data / "seen.json"))
    fresh = dedupe(items, db, digest_date)
    if use_semantic:
        fresh = semantic.dedupe(fresh, _richness, float(scfg.get("dedupe_threshold", 0.92)))

    # Upcoming contests skip scoring and sections entirely: they render in
    # their own calendar strip, every night until they start.
    upcoming = [it for it in fresh if it.evergreen]
    buckets = Scorer(cfg).route_and_filter([it for it in fresh if not it.evergreen])

    # Best-effort thumbnails, only for the items that survived routing.
    images.attach_images(buckets, cfg.get("images", {}))

    if args.no_summarize:
        for bucket in buckets.values():
            for it in bucket:
                it.summary = _fallback(it)
                it.detail = _fallback_detail(it)
        used_llm = False
    else:
        used_llm = summarize_all(buckets, cfg["groq"])

    faithfulness = verify.check(buckets, _fallback)

    # Learned like/dislike affinity, synced from the site via /api/feedback.
    # Applied after summarize (tag needs the LLM) and after scoring already
    # decided inclusion — this only reorders what's already in, so a learned
    # dislike sinks an item instead of silently hiding it.
    feedback_path = data / "feedback.json"
    taste = {}
    if use_semantic:
        semantic.attach_related(buckets, data / "archive", digest_date,
                                int(scfg.get("related_days", 14)),
                                float(scfg.get("related_threshold", 0.8)))
        taste = semantic.taste_boost(buckets, preferences.load_raw(feedback_path),
                                     float(scfg.get("taste_weight", 1.5)))
    preferences.apply(buckets, preferences.load_affinity(feedback_path), taste)

    output.pick_highlights(buckets, cfg)
    the_brief = brief_mod.build(buckets, cfg, use_llm=used_llm)

    kept = [it for b in buckets.values() for it in b]
    stats = {
        "fetched": len(items),
        "new_after_dedupe": len(fresh),
        "published": len(kept),
        "failed_sources": failed_sources,
        "summarizer": "groq" if used_llm else "fallback",
        "faithfulness": faithfulness,
        "brief": the_brief["generated"] if the_brief else "none",
    }
    output.write(buckets, cfg, digest_date, stats, data, brief=the_brief, upcoming=upcoming)
    db.mark(kept, digest_date)

    retention = int(cfg.get("seen_retention_days", 90))
    cutoff = (datetime.now(tz).date() - timedelta(days=retention)).isoformat()
    pruned = db.prune(cutoff)
    db.save()
    log.info("published %d items, pruned %d old seen-rows", len(kept), pruned)

    wcfg = cfg.get("weekly", {})
    today = date.fromisoformat(digest_date)
    if wcfg.get("enabled", True) and not args.no_summarize and (
            args.weekly or today.isoweekday() == int(wcfg.get("weekday", 7))):
        recap = weekly.build(data, cfg["groq"], today)
        if recap:
            log.info("weekly recap written to %s", weekly.write(recap, data))

    # A degraded night still ships (yesterday's site would be worse), but it
    # must not look like a healthy one: the workflow turns this into a red
    # run + a healthchecks.io /fail ping, so you hear about it the same day.
    degraded = []
    if not args.no_summarize and not used_llm:
        degraded.append("summaries fell back to raw abstracts")
    if not kept:
        degraded.append("published 0 items")
    if len(failed_sources) >= 3:
        degraded.append(f"{len(failed_sources)} sources failed")
    for reason in degraded:
        log.warning("DEGRADED: %s", reason)
    _report({"degraded": "true" if degraded else "false",
             "degraded_reason": "; ".join(degraded)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
