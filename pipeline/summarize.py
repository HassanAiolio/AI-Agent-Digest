"""Summarization via the Gemini API free tier, batched to stay far under quota.

One request per batch of items (default 12), so a typical night costs
~4-8 requests total. Any failure — missing key, quota change, network,
malformed response — degrades to truncated abstracts instead of killing
the run. The digest always ships.
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

ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent")

PROMPT = """You are writing one-line entries for a nightly technical digest \
read by a software engineer interested in AI/ML, embedded systems, \
competitive programming, and CS research.

For each item below, write a single summary of at most 35 words: concrete, \
factual, no hype words, no "this paper presents". Lead with what it is or \
what changed. If the item is a contest or a model release, state the key \
facts (date, size, license) when present.

Respond with ONLY a JSON array, no markdown fences, in this exact shape:
[{{"id": "<id>", "summary": "<text>"}}, ...]

Items:
{items}"""


def _fallback(it: Item) -> str:
    text = " ".join(it.abstract.split())
    return (text[:220] + "…") if len(text) > 220 else text


def _call_gemini(model: str, prompt: str, timeout: int) -> str:
    key = os.environ["GEMINI_API_KEY"]
    resp = requests.post(
        ENDPOINT.format(model=model),
        headers={"x-goog-api-key": key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 8192,
                # 2.5+ Flash models think by default and thinking tokens count
                # against maxOutputTokens, truncating the JSON output. This
                # task needs no reasoning, so turn thinking off entirely.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _parse(text: str) -> dict[str, str]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    return {d["id"]: d["summary"].strip() for d in data
            if isinstance(d, dict) and d.get("id") and d.get("summary")}


def summarize_all(buckets: dict[str, list[Item]], gcfg: dict) -> bool:
    """Fill item.summary in place. Returns True if Gemini was used."""
    items = [it for bucket in buckets.values() for it in bucket]
    for it in items:
        it.summary = _fallback(it)  # safe default before any API call

    if not os.environ.get("GEMINI_API_KEY"):
        log.warning("GEMINI_API_KEY not set — shipping fallback summaries")
        return False

    model = gcfg.get("model", "gemini-flash-latest")
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
        quota_exhausted = False
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            try:
                raw = _call_gemini(model, PROMPT.format(items=lines), timeout)
                summaries = _parse(raw)
                for it in batch:
                    if it.id in summaries:
                        it.summary = summaries[it.id]
                used_api = True
                break
            except requests.exceptions.HTTPError as e:
                log.warning("gemini batch failed (attempt %d): %s", attempt, e)
                if e.response is not None and e.response.status_code == 429:
                    quota_exhausted = True
                    break
                # 503 ("model overloaded") and similar are transient capacity
                # blips per Google's own guidance — retry with backoff instead
                # of giving up after one retry.
                if attempt < max_attempts:
                    time.sleep(min(pause * 2 ** attempt, 30))
            except Exception as e:
                log.warning("gemini batch failed (attempt %d): %s", attempt, e)
                if attempt < max_attempts:
                    time.sleep(min(pause * 2 ** attempt, 30))
        if quota_exhausted:
            log.warning("gemini quota/billing exhausted — shipping fallback "
                        "summaries for remaining items")
            break
        time.sleep(pause)
    return used_api
