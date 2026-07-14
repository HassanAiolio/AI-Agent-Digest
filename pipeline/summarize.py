"""Summarization via the Groq API free tier, batched to stay far under quota.

One request per batch of items (default 12), so a typical night costs
~4-8 requests total. Any failure — missing key, quota change, network,
malformed response — degrades to truncated abstracts instead of killing
the run. The digest always ships.

The prompt asks for an *adaptive* structure per item: a always-present
one-line summary (the safe fallback shape), plus an optional tag
(what kind of thing this is) and optional key_points — short factual
bullets (numbers, dates, license, benchmark deltas) pulled out only when
the source text actually has them. A blog opinion piece gets a plain
summary and no bullets; a model release gets a tag + 2-3 hard facts.
That way the reader gets exactly as much structure as the item earns,
without clicking through.
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
programming, and CS research. The reader wants to skim your entries and \
never need to click through to the source.

For each item below, produce:
- "summary": one or two sentences (max 45 words total), concrete and \
factual, no hype words, no "this paper presents". Lead with what it is or \
what changed, then why it matters if that fits.
- "tag": the single best fit from {tags}, or "" if none fit well.
- "key_points": a JSON array of 0-3 short factual strings (max 8 words \
each) — concrete extractable facts like model size, benchmark numbers, \
license, dates, version, deadline. ONLY include facts that are explicitly \
present in the text below. Leave this an empty array for opinion pieces, \
essays, or anything without hard facts to extract. Do not invent facts.

Respond with ONLY a JSON object, no markdown fences, in this exact shape:
{{"items": [{{"id": "<id>", "summary": "<text>", "tag": "<tag or empty>", \
"key_points": ["<fact>", ...]}}, ...]}}

Items:
{items}"""


def _fallback(it: Item) -> str:
    text = " ".join(it.abstract.split())
    return (text[:220] + "…") if len(text) > 220 else text


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
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


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

    if not os.environ.get("GROQ_API_KEY"):
        log.warning("GROQ_API_KEY not set — shipping fallback summaries")
        return False

    model = gcfg.get("model", "llama-3.3-70b-versatile")
    batch_size = int(gcfg.get("max_items_per_call", 12))
    max_chars = int(gcfg.get("max_abstract_chars", 900))
    timeout = int(gcfg.get("request_timeout", 60))
    pause = float(gcfg.get("sleep_between_calls", 3))

    used_api = False
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        lines = "\n\n".join(
            f"id: {it.id}\ntitle: {it.title}\nsource: {it.source}\n"
            f"text: {it.abstract[:max_chars]}"
            for it in batch
        )
        prompt = PROMPT.format(tags=", ".join(TAGS), items=lines)
        quota_exhausted = False
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            try:
                raw = _call_groq(model, prompt, timeout)
                results = _parse(raw)
                for it in batch:
                    r = results.get(it.id)
                    if r:
                        it.summary = r["summary"]
                        it.tag = r["tag"]
                        it.key_points = r["key_points"]
                used_api = True
                break
            except requests.exceptions.HTTPError as e:
                log.warning("groq batch failed (attempt %d): %s", attempt, e)
                if e.response is not None and e.response.status_code == 429:
                    quota_exhausted = True
                    break
                # 503 ("model overloaded") and similar are transient capacity
                # blips — retry with backoff instead of giving up after one try.
                if attempt < max_attempts:
                    time.sleep(min(pause * 2 ** attempt, 30))
            except Exception as e:
                log.warning("groq batch failed (attempt %d): %s", attempt, e)
                if attempt < max_attempts:
                    time.sleep(min(pause * 2 ** attempt, 30))
        if quota_exhausted:
            log.warning("groq quota/rate limit exhausted — shipping fallback "
                        "summaries for remaining items")
            break
        time.sleep(pause)
    return used_api
