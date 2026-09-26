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
    detail: str = ""                 # longer summary, shown on click-to-expand
    key_points: list[str] = field(default_factory=list)  # optional extracted facts
    tag: str = ""                    # optional content-type label, e.g. "Release"
    highlight: bool = False          # true for the night's top cross-section picks
    image: str = ""                  # optional og:image URL, best-effort
    # Upcoming events (contests) that should show every night until they
    # start, instead of once and then being swallowed by the seen-DB.
    evergreen: bool = False
    # Most similar item from a recent past edition, set by semantic.py:
    # {"title", "url", "date", "id"}. Empty when nothing is close enough.
    related: dict = field(default_factory=dict)

    def public_dict(self) -> dict:
        d = asdict(self)
        for private in ("weight", "abstract", "evergreen"):
            d.pop(private, None)
        return d


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
