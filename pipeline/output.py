"""Writes data/digest.json (latest) and data/archive/YYYY-MM-DD.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from models import Item


def upcoming_dict(it: Item) -> dict:
    return {"id": it.id, "title": it.title, "url": it.url, "source": it.source,
            "starts": it.published, "detail": it.abstract}


def pick_highlights(buckets: dict[str, list[Item]], cfg: dict) -> list[Item]:
    """Flag the night's top-scoring items across all sections. Runs before
    the brief is written, since the brief leads with these."""
    count = int(cfg.get("highlights", {}).get("count", 0))
    all_items = [it for b in buckets.values() for it in b]
    for it in all_items:
        it.highlight = False
    top = sorted(all_items, key=lambda i: (-i.score, i.title))[:count]
    for it in top:
        it.highlight = True
    return top


def write(buckets: dict[str, list[Item]], cfg: dict, digest_date: str,
          stats: dict, data_dir: Path, *, brief: dict | None = None,
          upcoming: list[Item] | None = None) -> dict:
    top = pick_highlights(buckets, cfg)

    sections = []
    for s in cfg["sections"]:
        items = buckets.get(s["id"], [])
        if not items:
            continue
        sections.append({
            "id": s["id"],
            "title": s["title"],
            "tier": s["tier"],
            "items": [it.public_dict() for it in items],
        })

    doc = {
        "date": digest_date,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": stats,
        "brief": brief,
        "upcoming": [upcoming_dict(it) for it in sorted(upcoming or [], key=lambda i: i.published or "")],
        "highlights": [it.public_dict() for it in top],
        "sections": sections,
    }

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "archive").mkdir(exist_ok=True)
    payload = json.dumps(doc, indent=2, ensure_ascii=False)
    (data_dir / "digest.json").write_text(payload, encoding="utf-8")
    (data_dir / "archive" / f"{digest_date}.json").write_text(payload, encoding="utf-8")
    return doc
