"""Summarization via the Groq API free tier, batched to stay far under quota.

One request per batch of items (default 12), so a typical night costs
~4-8 requests total. Any failure — missing key, quota change, network,
malformed response — degrades to truncated abstracts instead of killing
the run. The digest always ships.

The prompt asks for an *adaptive* structure per item, split across what's
always visible on the card (summary, tag, key_points) and what's behind a
click (detail). The card must be self-sufficient: summary carries the
headline fact instead of vague description, and key_points surfaces the
hard numbers (size, benchmark deltas, license, dates) right there — a
reader who never clicks still gets the important stuff. "detail" is bonus
depth for whoever does click (context, comparison, caveats), not a second
copy of facts that belong on the card.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

from models import Item

log = logging.getLogger("summarize")

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

TAGS = ["Release", "Research", "Contest", "Repo", "Analysis", "News"]

PROMPT = """You are writing entries for a nightly technical digest read by a \
software engineer interested in AI/ML, embedded systems, competitive \
programming, and CS research. Most readers only ever look at the card — \
summary, tag, and key_points — and never click through. That card alone \
must carry every important fact. "detail" is a bonus for the few who do \
click for more depth; it must never be the ONLY place a key fact appears.

For each item below, produce:
- "summary": 1-2 sentences (max 45 words), concrete and factual, no hype \
words, no "this paper presents". Lead with what it is or what changed. If \
there's a headline number, date, or name that matters, put it in this \
sentence itself — not only in key_points. A reader who reads only this \
sentence should still walk away with the single most important fact.
- "key_points": a JSON array of 0-3 short factual strings (max 8 words \
each) — the concrete numbers a reader would otherwise have to click \
through for: model size, benchmark deltas, license, price, dates, \
version, deadline. These render right on the card next to the summary. \
ONLY include facts explicitly present in the text below — never invent \
one. Empty array for opinion pieces or anything with no hard facts.
- "detail": 3-5 sentences (max 100 words) of material that is NOT already \
in summary or key_points — added context, how it compares to prior work, \
a caveat, a secondary use case, or why it matters beyond the headline \
fact. If you truly have nothing to add, still write 1-2 sentences of real \
elaboration rather than restating the summary in different words. No \
hype, no filler.
- "tag": the single best fit from {tags}, or "" if none fit well.

Respond with ONLY a JSON object, no markdown fences, in this exact shape:
{{"items": [{{"id": "<id>", "summary": "<text>", "key_points": ["<fact>", ...], \
"detail": "<text>", "tag": "<tag or empty>"}}]}}

Items:
{items}"""


def _truncate(text: str, chars: int) -> str:
    text = " ".join(text.split())
    return (text[:chars] + "…") if len(text) > chars else text


def _fallback(it: Item) -> str:
    return _truncate(it.abstract, 220)


def _fallback_detail(it: Item) -> str:
    return _truncate(it.abstract, 600)


def _call_groq(model: str, prompt: str, timeout: int) -> str:
    key = os.environ["GROQ_API_KEY"]
    resp = requests.post(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 6144,  # detail field adds ~100 words/item over the old summary-only shape
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _retry_after(e: requests.exceptions.HTTPError) -> float | None:
    """Seconds to wait before retrying a 429, per Groq's own guidance.
    Prefer the Retry-After header; Groq also states the wait in the error
    body (e.g. "Please try again in 7.66s") when the header is absent."""
    resp = e.response
    if resp is None:
        return None
    header = resp.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    m = re.search(r"try again in (\d+(?:\.\d+)?)s", resp.text or "", re.I)
    return float(m.group(1)) if m else None


def _parse(text: str) -> dict[str, dict]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    items = data["items"] if isinstance(data, dict) else data
    out = {}
    for d in items:
        if not (isinstance(d, dict) and d.get("id") and d.get("summary")):
            continue
        tag = d.get("tag") or ""
        points = d.get("key_points") or []
        out[d["id"]] = {
            "summary": d["summary"].strip(),
            "detail": (d.get("detail") or "").strip(),
            "tag": tag if tag in TAGS else "",
            "key_points": [p.strip() for p in points if isinstance(p, str) and p.strip()][:3],
        }
    return out


def summarize_all(buckets: dict[str, list[Item]], gcfg: dict) -> bool:
    """Fill item.summary (and tag/key_points where warranted) in place.
    Returns True if Groq was used."""
    items = [it for bucket in buckets.values() for it in bucket]
    for it in items:
        it.summary = _fallback(it)  # safe default before any API call
        it.detail = _fallback_detail(it)

    if not os.environ.get("GROQ_API_KEY"):
        log.warning("GROQ_API_KEY not set — shipping fallback summaries")
        return False

    model = gcfg.get("model", "llama-3.3-70b-versatile")
    batch_size = int(gcfg.get("max_items_per_call", 12))
    max_chars = int(gcfg.get("max_abstract_chars", 900))
    timeout = int(gcfg.get("request_timeout", 60))
    pause = float(gcfg.get("sleep_between_calls", 3))

    used_api = False
    consecutive_batch_failures = 0
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        lines = "\n\n".join(
            f"id: {it.id}\ntitle: {it.title}\nsource: {it.source}\n"
            f"text: {it.abstract[:max_chars]}"
            for it in batch
        )
        prompt = PROMPT.format(tags=", ".join(TAGS), items=lines)
        batch_ok = False
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            try:
                raw = _call_groq(model, prompt, timeout)
                results = _parse(raw)
                for it in batch:
                    r = results.get(it.id)
                    if r:
                        it.summary = r["summary"]
                        it.detail = r["detail"] or it.detail
                        it.tag = r["tag"]
                        it.key_points = r["key_points"]
                used_api = True
                batch_ok = True
                break
            except requests.exceptions.HTTPError as e:
                log.warning("groq batch failed (attempt %d): %s", attempt, e)
                if attempt >= max_attempts:
                    break
                if e.response is not None and e.response.status_code == 429:
                    # Free-tier 429s are almost always a per-minute rate
                    # limit that clears in seconds, not a hard daily quota.
                    # Groq tells us exactly how long to wait — respect it
                    # instead of giving up on the whole run over one hit.
                    wait = _retry_after(e)
                    time.sleep(min(wait, 60) if wait else min(pause * 2 ** attempt, 30))
                else:
                    # 503 ("model overloaded") and similar are transient
                    # capacity blips — retry with backoff.
                    time.sleep(min(pause * 2 ** attempt, 30))
            except Exception as e:
                log.warning("groq batch failed (attempt %d): %s", attempt, e)
                if attempt < max_attempts:
                    time.sleep(min(pause * 2 ** attempt, 30))
        if batch_ok:
            consecutive_batch_failures = 0
        else:
            consecutive_batch_failures += 1
            log.warning("batch starting at item %d exhausted retries — "
                        "keeping fallback summaries for it", start)
            if consecutive_batch_failures >= 2:
                log.warning("groq failing consistently — shipping fallback "
                            "summaries for remaining items")
                break
        time.sleep(pause)
    return used_api
