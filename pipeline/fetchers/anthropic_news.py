"""Anthropic news scraper.

FRAGILE: Anthropic publishes no official RSS feed, so this scrapes the
newsroom index for links. Second most likely thing to break after GitHub
trending. All markup coupling lives in _parse(). Each list entry carries a
<time> (date), a subject label and a title span; reading the link's whole
text glued them together ("Sep 23, 2026 Science Claude discovers…"), so the
title span is read on its own when present. The seen-DB ensures each post
appears in exactly one digest.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from models import Item

INDEX = "https://www.anthropic.com/news"
UA = "Mozilla/5.0 (X11; Linux x86_64) nightly-digest/1.0"


_DATE_PREFIX = re.compile(
    r"^[A-Z][a-z]{2} \d{1,2}, \d{4}\s+"
    r"(?:(?:Announcements|Product|Science|Policy|Research|Interpretability|Alignment"
    r"|Societal Impacts|Economic Research|Education|Event)\s+)?"
)


def _parse_date(text: str) -> str | None:
    try:
        return datetime.strptime(text, "%b %d, %Y").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    posts, seen = [], set()
    for a in soup.select('a[href^="/news/"]'):
        href = a.get("href", "")
        if href.rstrip("/") == "/news" or href in seen:
            continue
        # Class names are CSS-module hashes (…__title, …__date) that change
        # on every redeploy; match on the stable suffix only.
        title_el = a.select_one('[class*="title"]') or a.select_one("h2, h3, h4")
        title = (title_el or a).get_text(" ", strip=True)
        if title_el is None:
            title = _DATE_PREFIX.sub("", title)
        if len(title) < 8:  # skip nav chrome / "Read more" stubs
            continue
        time_el = a.find("time")
        seen.add(href)
        posts.append({"href": href, "title": title,
                      "published": _parse_date(time_el.get_text(strip=True)) if time_el else None})
    if not posts:
        raise RuntimeError("anthropic news: parsed 0 posts, markup likely changed")
    return posts[:15]


def fetch(src: dict, lookback: datetime) -> list[Item]:
    resp = requests.get(INDEX, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    return [
        Item(
            title=p["title"],
            url=urljoin(INDEX, p["href"]),
            source="Anthropic",
            published=p["published"],
        )
        for p in _parse(resp.text)
    ]
