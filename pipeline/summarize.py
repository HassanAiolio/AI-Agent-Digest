"""Summarization via the Groq API free tier, batched to stay far under quota.

One request per batch of items (default 6), so a typical night costs
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

import logging

import llm
from models import Item

log = logging.getLogger("summarize")

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


def _parse(data: dict | list) -> dict[str, dict]:
    items = data.get("items", []) if isinstance(data, dict) else data
    out = {}
    for d in items:
        if not (isinstance(d, dict) and d.get("id") and isinstance(d.get("summary"), str)):
            continue
        tag = d.get("tag") or ""
        points = d.get("key_points") or []
        out[d["id"]] = {
            "summary": d["summary"].strip(),
            "detail": (d.get("detail") or "").strip() if isinstance(d.get("detail"), str) else "",
            "tag": tag if tag in TAGS else "",
            "key_points": [p.strip() for p in points if isinstance(p, str) and p.strip()][:3],
        }
    return out


def summarize_all(buckets: dict[str, list[Item]], gcfg: dict) -> bool:
    """Fill item.summary (and tag/key_points where warranted) in place.
    Returns True if the LLM summarized at least one batch."""
    items = [it for bucket in buckets.values() for it in bucket]
    for it in items:
        it.summary = _fallback(it)  # safe default before any API call
        it.detail = _fallback_detail(it)

    if not llm.available():
        log.warning("GROQ_API_KEY not set — shipping fallback summaries")
        return False

    # Small batches on purpose: Groq counts max_tokens against the per-minute
    # token budget up front, and the old 12-item batch with a flat 6144-token
    # ceiling reserved more than the free tier's whole minute on busy
    # nights — every fallback night in the archive had 25+ items.
    batch_size = int(gcfg.get("max_items_per_call", 6))
    max_chars = int(gcfg.get("max_abstract_chars", 900))
    tokens_per_item = int(gcfg.get("output_tokens_per_item", 320))

    used_api = False
    consecutive_failures = 0
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        lines = "\n\n".join(
            f"id: {it.id}\ntitle: {it.title}\nsource: {it.source}\n"
            f"text: {it.abstract[:max_chars]}"
            for it in batch
        )
        prompt = PROMPT.format(tags=", ".join(TAGS), items=lines)
        try:
            results = _parse(llm.chat_json(prompt, gcfg, max_tokens=tokens_per_item * len(batch) + 300))
        except llm.LLMError as e:
            consecutive_failures += 1
            log.warning("batch at item %d failed for good (%s) — keeping fallback summaries", start, e)
            if consecutive_failures >= 2:
                log.warning("LLM failing consistently — fallback summaries for the rest")
                break
            continue
        consecutive_failures = 0
        used_api = True
        for it in batch:
            r = results.get(it.id)
            if r:
                it.summary = r["summary"]
                it.detail = r["detail"] or it.detail
                it.tag = r["tag"]
                it.key_points = r["key_points"]
    return used_api
