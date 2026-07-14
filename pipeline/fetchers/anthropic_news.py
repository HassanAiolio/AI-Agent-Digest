"""Anthropic news scraper.

FRAGILE: Anthropic publishes no official RSS feed, so this scrapes the
newsroom index for links. Second most likely thing to break after GitHub
trending. All markup coupling lives in _parse(). No dates are extracted
(the index doesn't reliably expose them); the seen-DB ensures each post
appears in exactly one digest.
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from models import Item

INDEX = "https://www.anthropic.com/news"
UA = "Mozilla/5.0 (X11; Linux x86_64) nightly-digest/1.0"


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    posts, seen = [], set()
    for a in soup.select('a[href^="/news/"]'):
        href = a.get("href", "")
        if href.rstrip("/") == "/news" or href in seen:
            continue
        title = a.get_text(" ", strip=True)
        if len(title) < 8:  # skip nav chrome / "Read more" stubs
            continue
        seen.add(href)
        posts.append({"href": href, "title": title})
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
        )
        for p in _parse(resp.text)
    ]
