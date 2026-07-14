"""Common item shape every fetcher normalizes into."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict


@dataclass
class Item:
    title: str
    url: str
    source: str                      # display name, e.g. "arXiv cs.LG"
    section: str | None = None       # fixed section id, or None to route by keywords
    published: str | None = None     # ISO 8601, UTC
    abstract: str = ""               # raw text used for scoring and summarization
    weight: float = 1.0              # source base weight from config
    points: int | None = None        # HN points / GitHub stars, when applicable
    score: float = 0.0
    id: str = ""                     # sha1 of canonical URL, set by dedupe stage
    summary: str = ""                # filled by summarizer (or fallback)

    def public_dict(self) -> dict:
        d = asdict(self)
        d.pop("weight", None)
        d.pop("abstract", None)
        return d


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
