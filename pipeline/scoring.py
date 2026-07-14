"""Relevance scoring and routing. Pure local string matching — no API calls.

score = source weight + matched keyword weights - matched negative weights

Items with a fixed section keep it and must clear include_threshold.
Items without one (Hacker News) go to their best-scoring section and must
clear the stricter route_threshold, or they're dropped as noise.
"""
from __future__ import annotations

import logging
import re

from models import Item

log = logging.getLogger("score")


def _compile(words: dict[str, float]) -> list[tuple[re.Pattern, float]]:
    out = []
    for word, w in words.items():
        # \b on both ends unless the keyword is a prefix like "fine-tun"
        pat = re.escape(word.lower())
        tail = r"" if word.endswith(("-", "tun")) else r"\b"
        out.append((re.compile(r"\b" + pat + tail), float(w)))
    return out


class Scorer:
    def __init__(self, cfg: dict):
        sc = cfg["scoring"]
        self.include_threshold = float(sc["include_threshold"])
        self.route_threshold = float(sc["route_threshold"])
        self.negative = _compile(sc.get("negative", {}))
        self.keywords = {
            section: _compile(words)
            for section, words in sc.get("keywords", {}).items()
        }
        self.sections = [s["id"] for s in cfg["sections"]]
        self.caps = {s["id"]: int(s["max_items"]) for s in cfg["sections"]}

    def _keyword_score(self, text: str, section: str) -> float:
        return sum(w for pat, w in self.keywords.get(section, []) if pat.search(text))

    def _penalty(self, text: str) -> float:
        return sum(w for pat, w in self.negative if pat.search(text))

    def route_and_filter(self, items: list[Item]) -> dict[str, list[Item]]:
        buckets: dict[str, list[Item]] = {s: [] for s in self.sections}
        dropped = 0
        for it in items:
            text = f"{it.title} {it.abstract}".lower()
            penalty = self._penalty(text)

            if it.section:  # fixed section
                kw = self._keyword_score(text, it.section)
                it.score = round(it.weight + kw - penalty, 2)
                if it.score >= self.include_threshold and it.section in buckets:
                    buckets[it.section].append(it)
                else:
                    dropped += 1
            else:  # route to best section
                best, best_kw = None, 0.0
                for s in self.sections:
                    k = self._keyword_score(text, s)
                    if k > best_kw:
                        best, best_kw = s, k
                if best is None or best_kw - penalty < self.route_threshold:
                    dropped += 1
                    continue
                it.section = best
                it.score = round(it.weight + best_kw - penalty, 2)
                buckets[best].append(it)

        for s, bucket in buckets.items():
            bucket.sort(key=lambda i: (-i.score, i.title))
            del bucket[self.caps[s]:]

        kept = sum(len(b) for b in buckets.values())
        log.info("scoring: %d kept across sections, %d dropped", kept, dropped)
        return buckets
