"""Fetcher registry. One source failing must never kill the run."""
from __future__ import annotations

import logging
import traceback
from datetime import datetime

from models import Item

from . import arxiv, rss, hackernews, codeforces, huggingface
from . import github_trending, anthropic_news

log = logging.getLogger("fetch")

REGISTRY = {
    "arxiv": arxiv.fetch,
    "rss": rss.fetch,
    "hackernews": hackernews.fetch,
    "codeforces": codeforces.fetch,
    "huggingface": huggingface.fetch,
    "github_trending": github_trending.fetch,
    "anthropic_news": anthropic_news.fetch,
}


def fetch_all(sources: list[dict], lookback: datetime) -> tuple[list[Item], list[str]]:
    """Run every configured source. Returns (items, failed_source_names)."""
    items: list[Item] = []
    failed: list[str] = []
    for src in sources:
        kind = src["kind"]
        name = src["name"]
        fn = REGISTRY.get(kind)
        if fn is None:
            log.error("unknown source kind %r for %s", kind, name)
            failed.append(name)
            continue
        try:
            got = fn(src, lookback)
            for it in got:
                it.weight = float(src.get("weight", 1.0))
                if it.section is None:
                    it.section = src.get("section")
            log.info("%-22s %3d items", name, len(got))
            items.extend(got)
        except Exception:
            log.error("source %s failed:\n%s", name, traceback.format_exc())
            failed.append(name)
    return items, failed
