"""Generic RSS/Atom fetcher. Covers every source that publishes a feed."""
from __future__ import annotations

import calendar
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from models import Item

UA = "nightly-digest/1.0 (+https://github.com/) personal RSS reader"


def _clean(html: str, limit: int = 1500) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return text[:limit]


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def fetch(src: dict, lookback: datetime) -> list[Item]:
    resp = requests.get(src["url"], headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)

    items: list[Item] = []
    for entry in feed.entries:
        when = _entry_time(entry)
        # Entries without a date are kept; the seen-DB stops repeats.
        if when is not None and when < lookback:
            continue
        link = entry.get("link", "")
        title = (entry.get("title") or "").strip()
        if not link or not title:
            continue
        items.append(Item(
            title=title,
            url=link,
            source=src["name"].replace("-", " "),
            published=when.isoformat() if when else None,
            abstract=_clean(entry.get("summary", "")),
        ))
    return items
