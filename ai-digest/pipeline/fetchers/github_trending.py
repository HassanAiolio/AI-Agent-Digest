"""GitHub trending scraper.

FRAGILE: GitHub has no official trending API, so this parses HTML.
Expected to be the first thing that breaks. All layout assumptions live
in _parse_page() below — when GitHub changes markup, fix only that
function. A total failure here degrades to "no repos section tonight";
it never kills the run (see fetchers/__init__.py).
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from models import Item

UA = "Mozilla/5.0 (X11; Linux x86_64) nightly-digest/1.0"


def _parse_page(html: str) -> list[dict]:
    """All GitHub-markup coupling is contained here."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("article.Box-row")
    out = []
    for row in rows:
        a = row.select_one("h2 a")
        if not a or not a.get("href"):
            continue
        repo = a["href"].strip("/")
        desc_el = row.select_one("p")
        stars_el = row.select_one('a[href$="/stargazers"]')
        stars = None
        if stars_el:
            raw = stars_el.get_text(strip=True).replace(",", "")
            stars = int(raw) if raw.isdigit() else None
        out.append({
            "repo": repo,
            "desc": desc_el.get_text(" ", strip=True) if desc_el else "",
            "stars": stars,
        })
    if not out:
        # Empty parse on a 200 response means the layout changed.
        raise RuntimeError("github trending: parsed 0 rows, markup likely changed")
    return out


def fetch(src: dict, lookback: datetime) -> list[Item]:
    items: list[Item] = []
    seen_repos: set[str] = set()
    for lang in src.get("languages", [""]):
        url = "https://github.com/trending"
        if lang:
            url += f"/{quote(str(lang), safe='')}"
        resp = requests.get(url, params={"since": "daily"},
                            headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        for r in _parse_page(resp.text):
            if r["repo"] in seen_repos:
                continue
            seen_repos.add(r["repo"])
            items.append(Item(
                title=r["repo"],
                url=f"https://github.com/{r['repo']}",
                source=f"GitHub trending{' · ' + str(lang) if lang else ''}",
                abstract=r["desc"],
                points=r["stars"],
            ))
    return items
