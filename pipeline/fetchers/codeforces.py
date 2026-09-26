"""Codeforces official API: upcoming contests within a configurable horizon.

Contests are evergreen: they skip the seen-DB and render in the "upcoming"
calendar every night until they start, instead of appearing once the night
they were announced and then never again."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from models import Item

API = "https://codeforces.com/api/contest.list"


def fetch(src: dict, lookback: datetime) -> list[Item]:
    horizon = timedelta(days=int(src.get("horizon_days", 10)))
    now = datetime.now(timezone.utc)
    resp = requests.get(API, params={"gym": "false"}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "OK":
        raise RuntimeError(f"codeforces API status: {payload.get('status')}")

    items: list[Item] = []
    for c in payload["result"]:
        if c.get("phase") != "BEFORE" or "startTimeSeconds" not in c:
            continue
        start = datetime.fromtimestamp(c["startTimeSeconds"], tz=timezone.utc)
        if start > now + horizon:
            continue
        hours = c.get("durationSeconds", 0) / 3600
        items.append(Item(
            title=c["name"],
            url=f"https://codeforces.com/contests/{c['id']}",
            source="Codeforces",
            published=start.isoformat(),
            abstract=(f"{c.get('type', '')} contest, {hours:.1f}h, "
                      f"starts {start.strftime('%a %d %b %H:%M UTC')}"),
            evergreen=True,
        ))
    return items
