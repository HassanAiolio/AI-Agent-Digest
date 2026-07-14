"""Hacker News via the Algolia API. Items carry no fixed section;
the scoring stage routes each one to its best-matching section or drops it."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from models import Item

API = "https://hn.algolia.com/api/v1/search_by_date"


def fetch(src: dict, lookback: datetime) -> list[Item]:
    min_points = int(src.get("min_points", 80))
    since = int(lookback.timestamp())
    resp = requests.get(API, params={
        "tags": "story",
        "numericFilters": f"points>{min_points},created_at_i>{since}",
        "hitsPerPage": 100,
    }, timeout=30)
    resp.raise_for_status()

    items: list[Item] = []
    for hit in resp.json().get("hits", []):
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        when = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)
        items.append(Item(
            title=hit.get("title", "").strip(),
            url=url,
            source="Hacker News",
            section=None,  # routed later
            published=when.isoformat(),
            abstract=hit.get("story_text") or "",
            points=hit.get("points"),
        ))
    return items
