"""Best-effort og:image scraping for item thumbnails.

Runs only on items that already survived scoring/routing — a couple dozen
a night, not the couple hundred fetched — with a short per-request timeout
and total silence on failure. A missing image is invisible to the reader
(the frontend just doesn't render a thumbnail), so this must never risk
the run the way the fragile HTML scrapers in fetchers/ can: any exception
here is caught and treated as "no image", nothing more.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from models import Item

log = logging.getLogger("images")

UA = "Mozilla/5.0 (X11; Linux x86_64) nightly-digest/1.0"

# arXiv abstract pages and Codeforces contest pages never carry a useful
# preview image — skip them outright instead of wasting a request.
_SKIP_SOURCE_SUBSTRINGS = ("arxiv", "codeforces")


def _skip(it: Item) -> bool:
    s = it.source.lower()
    return any(sub in s for sub in _SKIP_SOURCE_SUBSTRINGS)


def _fetch_og_image(url: str, timeout: int) -> str | None:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ("og:image", "twitter:image"):
            tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            content = (tag.get("content") or "").strip() if tag else ""
            if not content:
                continue
            # og:image is often relative ("/img/card.png") or protocol-
            # relative; resolve against the page. Only https is kept: the
            # site is served over https and next/image rejects anything else.
            absolute = urljoin(resp.url or url, content)
            if urlsplit(absolute).scheme == "https":
                return absolute
    except Exception as e:
        log.debug("no image for %s: %s", url, e)
    return None


def attach_images(buckets: dict[str, list[Item]], cfg: dict) -> None:
    """Fills item.image in place for items likely to have a preview image."""
    if not cfg.get("enabled", True):
        return
    timeout = int(cfg.get("timeout", 5))

    workers = int(cfg.get("workers", 8))

    candidates = [it for b in buckets.values() for it in b if not _skip(it)]
    # I/O-bound and independent per item: a thread pool turns ~25 serial
    # 5-second worst cases into a couple of seconds total.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda it: _fetch_og_image(it.url, timeout), candidates))
    found = 0
    for it, image in zip(candidates, results):
        if image:
            it.image = image
            found += 1
    log.info("images: %d/%d candidates got a thumbnail", found, len(candidates))
