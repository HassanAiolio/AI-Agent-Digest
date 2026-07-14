"""arXiv official API. Stable, documented, no auth."""
from __future__ import annotations

import calendar
from datetime import datetime, timezone

import feedparser
import requests

from models import Item

API = "https://export.arxiv.org/api/query"


def fetch(src: dict, lookback: datetime) -> list[Item]:
    query = " OR ".join(f"cat:{c}" for c in src["categories"])
    resp = requests.get(API, params={
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": src.get("max_results", 40),
    }, timeout=45)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)

    items: list[Item] = []
    for entry in feed.entries:
        t = entry.get("published_parsed")
        if not t:
            continue
        when = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
        if when < lookback:
            continue
        cats = ",".join(c["term"] for c in entry.get("tags", [])[:3])
        items.append(Item(
            title=" ".join(entry.title.split()),
            url=entry.get("link", entry.get("id", "")),
            source=f"arXiv {cats.split(',')[0] if cats else ''}".strip(),
            published=when.isoformat(),
            abstract=" ".join(entry.get("summary", "").split()),
        ))
    return items
