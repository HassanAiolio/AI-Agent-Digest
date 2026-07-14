"""Hugging Face Hub API: trending models. Public, no auth.
No date filter here; the seen-DB guarantees each model appears once."""
from __future__ import annotations

from datetime import datetime

import requests

from models import Item

API = "https://huggingface.co/api/models"


def fetch(src: dict, lookback: datetime) -> list[Item]:
    resp = requests.get(API, params={
        "sort": "trendingScore",
        "direction": -1,
        "limit": int(src.get("limit", 15)),
    }, timeout=30)
    resp.raise_for_status()

    items: list[Item] = []
    for m in resp.json():
        model_id = m.get("modelId") or m.get("id")
        if not model_id:
            continue
        bits = [b for b in (
            m.get("pipeline_tag"),
            f"{m.get('downloads', 0):,} downloads" if m.get("downloads") else None,
            f"{m.get('likes', 0)} likes" if m.get("likes") else None,
        ) if b]
        items.append(Item(
            title=f"Model: {model_id}",
            url=f"https://huggingface.co/{model_id}",
            source="HF trending",
            published=m.get("createdAt"),
            abstract=" · ".join(bits),
            points=m.get("likes"),
        ))
    return items
