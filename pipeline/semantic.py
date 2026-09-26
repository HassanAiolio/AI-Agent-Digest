"""Meaning-level signals from sentence embeddings. Runs locally (fastembed +
BAAI/bge-small-en-v1.5, ~70 MB ONNX, CPU), so it costs nothing per night.

Three jobs, each strictly additive on top of the keyword pipeline:

1. dedupe()        — merge items that are the same story under different
                     titles (an arXiv paper and the blog post announcing it),
                     which the fuzzy-title layer in dedupe.py can't see.
2. attach_related() — link each item to the closest item from the last two
                     weeks of editions, rendered as "Previously in the digest".
3. taste_boost()   — score items by similarity to titles you liked minus
                     titles you disliked, so preference learning generalizes
                     past exact tag/source matches.

If fastembed isn't installed or the model can't load (offline CI, a
download hiccup), every function here is a logged no-op and the night
ships exactly as it would have without embeddings.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

from rapidfuzz import fuzz

from models import Item

log = logging.getLogger("semantic")

MODEL = "BAAI/bge-small-en-v1.5"

_model = None
_load_failed = False


def _embedder():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from fastembed import TextEmbedding
        cache = os.environ.get("FASTEMBED_CACHE") or str(Path.home() / ".cache" / "fastembed")
        _model = TextEmbedding(MODEL, cache_dir=cache)
    except Exception as e:  # ImportError, download failure, onnxruntime issue
        log.warning("embeddings unavailable (%s) — skipping semantic stages", e)
        _load_failed = True
    return _model


def _embed(texts: list[str]):
    """Unit-normalized vectors as a numpy array, or None if unavailable."""
    model = _embedder()
    if model is None or not texts:
        return None
    import numpy as np
    vecs = np.array(list(model.embed(texts)), dtype="float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.clip(norms, 1e-9, None)


def _text(it: Item) -> str:
    return f"{it.title}. {it.summary or it.abstract[:300]}"


def dedupe(items: list[Item], richness, threshold: float = 0.925) -> list[Item]:
    """Drop near-identical stories, keeping the richer duplicate."""
    if len(items) < 2:
        return items
    ordered = sorted(items, key=richness, reverse=True)
    vecs = _embed([f"{it.title}. {it.abstract[:300]}" for it in ordered])
    if vecs is None:
        return items
    keep: list[int] = []
    for i in range(len(ordered)):
        if ordered[i].evergreen or not keep or float((vecs[keep] @ vecs[i]).max()) < threshold:
            keep.append(i)
    merged = len(ordered) - len(keep)
    if merged:
        log.info("semantic dedupe merged %d near-duplicate stories", merged)
    return [ordered[i] for i in keep]


def _recent_archive(archive_dir: Path, today: str, days: int) -> list[dict]:
    end = date.fromisoformat(today)
    out = []
    for n in range(1, days + 1):
        d = (end - timedelta(days=n)).isoformat()
        f = archive_dir / f"{d}.json"
        if not f.exists():
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for s in doc.get("sections", []):
            for it in s.get("items", []):
                out.append({"title": it["title"], "url": it["url"], "id": it["id"],
                            "summary": it.get("summary", ""), "date": d,
                            "source": it.get("source", "")})
    return out


# Listing sources whose entries all read alike ("Model: org/name-GGUF",
# "owner/repo — a CLI for X"): similarity between two of them says more
# about the template than about the topic.
_LISTINGS = ("hf trending", "github trending")


def _is_listing(source: str) -> bool:
    return source.lower().startswith(_LISTINGS)


def _worth_linking(it: Item, past: dict) -> bool:
    if past["url"] == it.url:
        return False
    if _is_listing(it.source) and _is_listing(past["source"]):
        return False
    # Recurring series ("Security updates for Friday" every week) are
    # near-identical titles, not related coverage.
    return fuzz.ratio(it.title.lower(), past["title"].lower()) < 80


def attach_related(buckets: dict[str, list[Item]], archive_dir: Path, today: str,
                   days: int = 14, threshold: float = 0.78) -> int:
    items = [it for b in buckets.values() for it in b]
    past = _recent_archive(archive_dir, today, days)
    if not items or not past:
        return 0
    now_vecs = _embed([_text(it) for it in items])
    if now_vecs is None:
        return 0
    past_vecs = _embed([f"{p['title']}. {p['summary']}" for p in past])
    sims = now_vecs @ past_vecs.T
    linked = 0
    for i, it in enumerate(items):
        for j in sims[i].argsort()[::-1][:5]:
            if float(sims[i, j]) < threshold:
                break
            p = past[int(j)]
            if _worth_linking(it, p):
                it.related = {"title": p["title"], "url": p["url"], "date": p["date"], "id": p["id"]}
                linked += 1
                break
    log.info("related: linked %d/%d items to past coverage", linked, len(items))
    return linked


def taste_boost(buckets: dict[str, list[Item]], feedback: dict, weight: float = 1.5) -> dict[str, float]:
    """{item id: boost} from similarity to liked vs disliked titles.
    Boost is in [-weight, +weight]; empty when there are no titled votes."""
    liked = [v["title"] for v in feedback.values() if isinstance(v, dict) and v.get("vote") == 1 and v.get("title")]
    disliked = [v["title"] for v in feedback.values() if isinstance(v, dict) and v.get("vote") == -1 and v.get("title")]
    items = [it for b in buckets.values() for it in b]
    if not items or not (liked or disliked):
        return {}
    vecs = _embed([_text(it) for it in items])
    if vecs is None:
        return {}

    def centroid(titles):
        if not titles:
            return None
        v = _embed(titles).mean(axis=0)
        return v / max(float((v @ v) ** 0.5), 1e-9)

    pos, neg = centroid(liked), centroid(disliked)
    raw = []
    for i in range(len(items)):
        s = 0.0
        if pos is not None:
            s += float(vecs[i] @ pos)
        if neg is not None:
            s -= float(vecs[i] @ neg)
        raw.append(s)
    # Unrelated English sentences still score ~0.3-0.5 cosine with this
    # model, so absolute values mean little. Centre on tonight's mean: the
    # boost says "closer to your taste than tonight's average item".
    mean = sum(raw) / len(raw)
    out = {}
    for it, s in zip(items, raw):
        out[it.id] = round(max(-weight, min(weight, (s - mean) * weight * 4)), 2)
    log.info("taste: boosted %d items from %d liked / %d disliked titles",
             len(out), len(liked), len(disliked))
    return out
