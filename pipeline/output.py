"""Writes data/digest.json (latest) and data/archive/YYYY-MM-DD.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from models import Item


def write(buckets: dict[str, list[Item]], cfg: dict, digest_date: str,
          stats: dict, data_dir: Path) -> dict:
    count = int(cfg.get("highlights", {}).get("count", 0))
    all_items = [it for b in buckets.values() for it in b]
    top = sorted(all_items, key=lambda i: (-i.score, i.title))[:count]
    for it in top:
        it.highlight = True

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
        "highlights": [it.public_dict() for it in top],
        "sections": sections,
    }

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "archive").mkdir(exist_ok=True)
    payload = json.dumps(doc, indent=2, ensure_ascii=False)
    (data_dir / "digest.json").write_text(payload, encoding="utf-8")
    (data_dir / "archive" / f"{digest_date}.json").write_text(payload, encoding="utf-8")
    return doc
