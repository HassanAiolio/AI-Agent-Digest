"""Fetchers against recorded responses. The HTML scrapers are the ones that
break when a site changes its markup; these tests make that a red CI run
instead of a silently empty section. Refresh a fixture by saving the live
page (trimmed to a few entries) over the file in tests/fixtures/."""
import re
from datetime import datetime, timedelta, timezone

from pathlib import Path

import pytest

import images
from fetchers import anthropic_news, codeforces, github_trending, hackernews, rss
from models import Item


class FakeResponse:
    def __init__(self, text="", payload=None, url=""):
        self.text = text
        self.content = text.encode("utf-8")
        self._payload = payload
        self.url = url
        self.headers = {}
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_github_trending_parses_recorded_page(fixture_text):
    rows = github_trending._parse_page(fixture_text("github_trending.html"))
    assert len(rows) == 3
    for r in rows:
        assert r["repo"].count("/") == 1, r
        assert isinstance(r["stars"], int) and r["stars"] > 0, r
    assert rows[0]["desc"]


def test_github_trending_empty_markup_raises():
    with pytest.raises(RuntimeError, match="markup likely changed"):
        github_trending._parse_page("<html><body>redesigned</body></html>")


def test_anthropic_news_titles_have_no_date_or_category(fixture_text):
    posts = anthropic_news._parse(fixture_text("anthropic_news.html"))
    assert len(posts) >= 5
    for p in posts:
        assert not re.match(r"[A-Z][a-z]{2} \d{1,2}, \d{4}", p["title"]), p["title"]
        assert not p["title"].startswith(("Announcements", "Science", "Product")), p["title"]
        assert p["published"] and p["published"].startswith("2026-"), p
    assert posts[0]["title"] == "Claude discovers a novel enzyme system with CRISPR-like repeats"


def test_anthropic_news_strips_prefix_without_title_span():
    html = '<a href="/news/x">Aug 31, 2026 Announcements Improving our security efforts</a>' \
           '<a href="/news/y">Aug 30, 2026 Improving something else entirely</a>'
    titles = [p["title"] for p in anthropic_news._parse(html)]
    assert titles == ["Improving our security efforts", "Improving something else entirely"]


def test_hackernews(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {"hits": [
        {"objectID": "1", "title": " Show HN: a RISC-V emulator ", "url": "https://e.com/a",
         "created_at_i": now, "points": 120, "story_text": None},
        {"objectID": "2", "title": "Ask HN: text post", "url": None,
         "created_at_i": now, "points": 90, "story_text": "body"},
    ]}
    monkeypatch.setattr(hackernews.requests, "get", lambda *a, **k: FakeResponse(payload=payload))
    items = hackernews.fetch({"min_points": 80}, datetime.now(timezone.utc) - timedelta(hours=30))
    assert [i.title for i in items] == ["Show HN: a RISC-V emulator", "Ask HN: text post"]
    assert items[1].url == "https://news.ycombinator.com/item?id=2"
    assert items[0].section is None and items[1].abstract == "body"


def test_codeforces_contests_are_evergreen(monkeypatch):
    soon = int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp())
    far = int((datetime.now(timezone.utc) + timedelta(days=40)).timestamp())
    payload = {"status": "OK", "result": [
        {"id": 1, "name": "Codeforces Round 1 (Div. 2)", "phase": "BEFORE",
         "startTimeSeconds": soon, "durationSeconds": 7200, "type": "CF"},
        {"id": 2, "name": "Far away round", "phase": "BEFORE",
         "startTimeSeconds": far, "durationSeconds": 7200, "type": "CF"},
        {"id": 3, "name": "Finished", "phase": "FINISHED", "startTimeSeconds": soon},
    ]}
    monkeypatch.setattr(codeforces.requests, "get", lambda *a, **k: FakeResponse(payload=payload))
    items = codeforces.fetch({"horizon_days": 10}, datetime.now(timezone.utc))
    assert [i.title for i in items] == ["Codeforces Round 1 (Div. 2)"]
    assert items[0].evergreen and "2.0h" in items[0].abstract


def test_rss_filters_old_entries(monkeypatch):
    now = datetime.now(timezone.utc)
    fmt = "%a, %d %b %Y %H:%M:%S +0000"
    feed = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
      <item><title>Fresh post</title><link>https://b.com/1</link>
        <pubDate>{now.strftime(fmt)}</pubDate><description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description></item>
      <item><title>Old post</title><link>https://b.com/2</link>
        <pubDate>{(now - timedelta(days=5)).strftime(fmt)}</pubDate></item>
    </channel></rss>"""
    monkeypatch.setattr(rss.requests, "get", lambda *a, **k: FakeResponse(text=feed))
    items = rss.fetch({"url": "https://b.com/feed", "name": "some-blog"}, now - timedelta(hours=30))
    assert [i.title for i in items] == ["Fresh post"]
    assert items[0].abstract == "Hello world" and items[0].source == "some blog"


def test_og_image_resolves_relative_and_rejects_http(monkeypatch):
    pages = {
        "https://site.com/post": '<meta property="og:image" content="/img/card.png">',
        "https://other.com/p": '<meta property="og:image" content="http://insecure.com/x.png">',
    }
    monkeypatch.setattr(images.requests, "get",
                        lambda url, **k: FakeResponse(text=pages[url], url=url))
    assert images._fetch_og_image("https://site.com/post", 5) == "https://site.com/img/card.png"
    assert images._fetch_og_image("https://other.com/p", 5) is None


def test_images_skip_sources_without_previews():
    assert images._skip(Item(title="t", url="https://arxiv.org/abs/1", source="arXiv cs.LG"))
    assert images._skip(Item(title="t", url="https://codeforces.com/c/1", source="Codeforces"))
    assert not images._skip(Item(title="t", url="https://openai.com/x", source="openai blog"))


def test_fixture_files_are_small():
    # Fixtures are trimmed on purpose; a full saved page is ~600 KB of noise.
    for f in (Path(__file__).parent / "fixtures").iterdir():
        assert f.stat().st_size < 64_000, f"{f.name} should be trimmed to a few entries"
