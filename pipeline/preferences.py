"""Learns from like/dislike feedback synced from the site.

Feedback lives in data/feedback.json, written by the /api/feedback route
(which commits directly to the repo — same pattern as the nightly bot's own
data commits). Votes are aggregated into a small per-tag/per-source affinity
score and folded into item.score as a final boost, after scoring.py has
already decided what's included. A learned dislike never silently hides a
source; it only sinks the item in its section and makes it less likely to
be picked as a highlight. Missing or malformed feedback.json degrades to no
boost at all — this is a nice-to-have layered on scoring, never load-bearing.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from models import Item

log = logging.getLogger("preferences")

TAG_WEIGHT = 0.6
SOURCE_WEIGHT = 0.4
CLAMP = 3.0  # cap per tag/source so one voting streak can't dominate scoring


def load_affinity(path: Path) -> dict[str, dict[str, float]]:
    """Returns {"tags": {tag: score}, "sources": {source: score}}."""
    tags: dict[str, float] = {}
    sources: dict[str, float] = {}
    if not path.exists():
        return {"tags": tags, "sources": sources}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("could not read %s: %s", path, e)
        return {"tags": tags, "sources": sources}

    events = raw.values() if isinstance(raw, dict) else raw
    for ev in events:
        if not isinstance(ev, dict):
            continue
        vote = ev.get("vote")
        if vote not in (1, -1):
            continue
        if ev.get("tag"):
            tags[ev["tag"]] = tags.get(ev["tag"], 0.0) + vote
        if ev.get("source"):
            sources[ev["source"]] = sources.get(ev["source"], 0.0) + vote

    tags = {k: max(-CLAMP, min(CLAMP, v)) for k, v in tags.items()}
    sources = {k: max(-CLAMP, min(CLAMP, v)) for k, v in sources.items()}
    log.info("loaded preference affinity: %d tags, %d sources", len(tags), len(sources))
    return {"tags": tags, "sources": sources}


def apply(buckets: dict[str, list[Item]], affinity: dict[str, dict[str, float]]) -> None:
    """Boosts item.score in place from learned affinity, then re-sorts each
    bucket. Never adds or removes items — inclusion was already decided."""
    tags = affinity.get("tags", {})
    sources = affinity.get("sources", {})
    if not tags and not sources:
        return
    for bucket in buckets.values():
        for it in bucket:
            boost = tags.get(it.tag, 0.0) * TAG_WEIGHT + sources.get(it.source, 0.0) * SOURCE_WEIGHT
            if boost:
                it.score = round(it.score + boost, 2)
        bucket.sort(key=lambda i: (-i.score, i.title))
