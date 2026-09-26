"""Faithfulness check: every hard fact the LLM puts on a card must be
traceable to the source text it was given.

The prompt already says "only include facts explicitly present", but a
prompt is a request, not a guarantee. This stage checks the part that is
cheap to check mechanically: numbers. A key point like "70B params, MIT
license" carries the tokens 70 and B; if "70" never appears in the title
or abstract, the model invented it and the key point is dropped before it
reaches the reader. Summaries aren't dropped (the card needs one), but an
unsupported number in a summary falls the item back to its abstract.

Key points with no numbers ("Apache-2.0 license", "open weights") can't
be verified this way and are kept; they are counted separately so the
reported rate stays honest about what was actually checked.
"""
from __future__ import annotations

import logging
import re

from models import Item

log = logging.getLogger("verify")

# 70, 1.5, 2,048, 3.1.4, 2026-09-26, 12%, $40 — the digit runs are what
# gets checked; units and words around them are ignored.
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    out = set()
    for raw in _NUMBER.findall(text):
        n = raw.replace(",", "")
        # Single digits ("3 models", "v2") are too common to prove anything
        # and too easy to phrase differently ("three"); skip them.
        if len(n.replace(".", "")) >= 2:
            out.add(n)
    return out


def _normalize(text: str) -> str:
    # "2,048" in the source and "2048" in the summary are the same number.
    return re.sub(r"(?<=\d),(?=\d{3})", "", text)


def _supported(claim: str, source: str) -> bool:
    return all(n in source for n in _numbers(claim))


def check(buckets: dict[str, list[Item]], fallback_summary) -> dict:
    """Drop unsupported key points and summaries in place. Returns stats:
    {"checked", "supported", "dropped", "unverifiable", "summaries_reverted", "rate"}."""
    checked = supported = dropped = unverifiable = reverted = 0
    for bucket in buckets.values():
        for it in bucket:
            source = _normalize(f"{it.title} {it.abstract}")

            kept = []
            for point in it.key_points:
                if not _numbers(point):
                    unverifiable += 1
                    kept.append(point)
                    continue
                checked += 1
                if _supported(_normalize(point), source):
                    supported += 1
                    kept.append(point)
                else:
                    dropped += 1
                    log.info("dropped unsupported key point %r (%s)", point, it.title[:60])
            it.key_points = kept

            summary_numbers = _numbers(_normalize(it.summary))
            if summary_numbers and it.abstract:
                checked += 1
                if all(n in source for n in summary_numbers):
                    supported += 1
                else:
                    reverted += 1
                    log.info("summary for %r had unsupported numbers, reverting", it.title[:60])
                    it.summary = fallback_summary(it)

    rate = round(supported / checked, 4) if checked else None
    log.info("faithfulness: %d/%d numeric claims supported, %d key points dropped, "
             "%d summaries reverted", supported, checked, dropped, reverted)
    return {
        "checked": checked,
        "supported": supported,
        "dropped": dropped,
        "unverifiable": unverifiable,
        "summaries_reverted": reverted,
        "rate": rate,
    }
