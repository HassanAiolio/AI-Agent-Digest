"""The morning brief: a newsletter-style lede written over tonight's items.

Styled after Morning Brew — a one-line greeting with some personality,
three short stories told conversationally with a bolded lead-in and a
"why it matters" line, a quick-hits list, and a number of the day. It is
written *from the already-summarized items*, never from the open web, and
every story must cite the item ids it draws on so the page can link each
story to its card below.

One LLM call per night. Anything that fails validation is dropped rather
than trusted, and a total failure falls back to a plain brief built from
the top picks, so the section is always there.
"""
from __future__ import annotations

import logging
import re

import llm
from models import Item

log = logging.getLogger("brief")

PROMPT = """You write the top section of a nightly tech newsletter in the voice of Morning Brew: a smart friend explaining the news. Conversational, confident, a little cheeky; short sentences; one good joke beats three weak ones. Readers are software engineers into AI/ML, embedded systems, competitive programming and CS research, and should know what happened overnight in under two minutes.

Voice rules:
- Talk to the reader ("you", "your"). Use contrast and specifics, not adjectives.
- Humor comes from the facts themselves (an ironic detail, an understatement), never from forced puns on every line.
- Explain jargon in a few words when a non-specialist engineer might trip.
- Banned phrases: "making waves", "game-changer", "buzz", "sip", "coffee", "exciting", "revolutionize", "landscape", "delve", "in the world of", "stay tuned", "dive in", "it's worth noting".

Style example (different news, for tone only — never reuse its facts):
  greeting: "Good morning. Three chip vendors shipped RISC-V boards overnight, and not one of them mentioned AI in the press release. Growth."
  headline: "The kernel gets a Rust babysitter"
  body: "**Memory safety, but make it mainline:** Linux 7.3 merges its first Rust-only driver, a GPU scheduler that previously crashed about once a week in testing. The C version stays for now — nobody is deleting code on a Friday."
  why: "If you maintain drivers, Rust just went from experiment to review checklist."

Use ONLY the items below. Never add facts, numbers, names or dates that are not in them.

Produce a JSON object with exactly these keys:
- "greeting": 1-2 sentences (max 30 words). Start with "Good morning." then a specific, lightly funny observation about tonight's actual news. No emojis.
- "stories": exactly 3 objects, the three most important or interesting developments, each:
    "kicker": 1-3 word topic label, e.g. "Open models", "Embedded", "Research".
    "headline": max 8 words, punchy and specific.
    "body": 2-3 short sentences (max 65 words). Start with your own bolded lead-in phrase (3-7 words that frame the story, wrapped in ** and ending with a colon inside the bold), then the story in plain language with concrete facts from the items.
    "why": one sentence (max 25 words) on why it matters to an engineer.
    "ids": array of the item ids this story draws on (at least one).
- "quick_hits": 4-6 objects {{"text": "...", "id": "<item id>"}} — one line each (max 20 words), starting with a 1-3 word **bold** label and a colon. Do not repeat the three stories.
- "number": {{"value": "...", "label": "...", "id": "<item id>"}} — the most striking figure in tonight's items (value max 8 characters, e.g. "70B", "3x", "41%"; label max 14 words saying what it measures). It must appear in that item's text. Use null if no item has a good number.
- "sign_off": one short, warm closing line with a wink (max 14 words).

No emojis anywhere.

Respond with ONLY the JSON object.

Items:
{items}"""


def _candidates(buckets: dict[str, list[Item]], limit: int) -> list[Item]:
    """Highlights first, then the best remaining item of each section in
    turn, so the brief spans sections instead of being five arXiv papers."""
    all_items = sorted((it for b in buckets.values() for it in b),
                       key=lambda i: (-i.score, i.title))
    picked = [it for it in all_items if it.highlight]
    seen = {it.id for it in picked}
    queues = [[it for it in b if it.id not in seen] for b in buckets.values()]
    while len(picked) < limit and any(queues):
        for q in queues:
            if q and len(picked) < limit:
                picked.append(q.pop(0))
    return picked[:limit]


def _format(items: list[Item], section_titles: dict[str, str]) -> str:
    blocks = []
    for it in items:
        facts = "; ".join(it.key_points)
        blocks.append(
            f"id: {it.id}\nsection: {section_titles.get(it.section or '', it.section)}\n"
            f"title: {it.title}\nsource: {it.source}\nsummary: {it.summary}"
            + (f"\nfacts: {facts}" if facts else "")
            + (f"\npoints: {it.points}" if it.points else "")
        )
    return "\n\n".join(blocks)


# Models sometimes echo the instruction instead of following it.
_LITERAL_LEAD = re.compile(r"^\*\*\s*(?:bold(?:ed)?\s+)?lead[- ]?in(?: phrase)?\s*:?\s*\*\*\s*:?\s*", re.I)


_EMOJI = re.compile("[🀀-🫿☀-➿️]")


def _clean(text, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    text = _LITERAL_LEAD.sub("", " ".join(_EMOJI.sub("", text).split()))
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _validate(data: dict, by_id: dict[str, Item]) -> dict | None:
    stories = []
    for s in data.get("stories") or []:
        if not isinstance(s, dict):
            continue
        ids = [i for i in (s.get("ids") or []) if isinstance(i, str) and i in by_id]
        headline, body = _clean(s.get("headline"), 90), _clean(s.get("body"), 520)
        if not (ids and headline and body):
            continue
        stories.append({
            "kicker": _clean(s.get("kicker"), 30),
            "headline": headline,
            "body": body,
            "why": _clean(s.get("why"), 220),
            "ids": ids[:3],
        })
    if len(stories) < 2:
        return None

    story_ids = {i for s in stories for i in s["ids"]}
    hits = []
    for h in data.get("quick_hits") or []:
        if isinstance(h, dict) and h.get("id") in by_id and h["id"] not in story_ids:
            text = _clean(h.get("text"), 200)
            if text:
                hits.append({"text": text, "id": h["id"]})

    number = None
    n = data.get("number")
    if isinstance(n, dict) and n.get("id") in by_id:
        value = _clean(n.get("value"), 12)
        it = by_id[n["id"]]
        source = f"{it.title} {it.abstract} {it.summary} {' '.join(it.key_points)}".replace(",", "")
        digits = re.findall(r"\d+(?:\.\d+)?", value.replace(",", ""))
        # Same rule as verify.py: the figure must be traceable to its item.
        if value and digits and all(d in source for d in digits):
            number = {"value": value, "label": _clean(n.get("label"), 110), "id": n["id"]}

    greeting = _clean(data.get("greeting"), 200) or "Good morning."
    return {
        "greeting": greeting,
        "stories": stories[:3],
        "quick_hits": hits[:6],
        "number": number,
        "sign_off": _clean(data.get("sign_off"), 120),
        "generated": "llm",
    }


def fallback(buckets: dict[str, list[Item]], section_titles: dict[str, str]) -> dict | None:
    items = _candidates(buckets, 9)
    if not items:
        return None
    return {
        "greeting": "Good morning. Here's what came through overnight.",
        "stories": [{
            "kicker": section_titles.get(it.section or "", ""),
            "headline": it.title,
            "body": it.summary,
            "why": "",
            "ids": [it.id],
        } for it in items[:3]],
        "quick_hits": [{"text": it.title, "id": it.id} for it in items[3:8]],
        "number": None,
        "sign_off": "",
        "generated": "fallback",
    }


def build(buckets: dict[str, list[Item]], cfg: dict, use_llm: bool) -> dict | None:
    section_titles = {s["id"]: s["title"] for s in cfg["sections"]}
    bcfg = cfg.get("brief", {})
    if not bcfg.get("enabled", True):
        return None
    items = _candidates(buckets, int(bcfg.get("max_items", 14)))
    if len(items) < 3:
        return fallback(buckets, section_titles)
    if not (use_llm and llm.available()):
        return fallback(buckets, section_titles)
    prompt = PROMPT.format(items=_format(items, section_titles))
    try:
        data = llm.chat_json(prompt, cfg["groq"], max_tokens=int(bcfg.get("max_tokens", 2200)))
    except llm.LLMError as e:
        log.warning("brief LLM call failed (%s) — plain brief", e)
        return fallback(buckets, section_titles)
    brief = _validate(data, {it.id: it for it in items})
    if brief is None:
        log.warning("brief failed validation — plain brief")
        return fallback(buckets, section_titles)
    log.info("brief: %d stories, %d quick hits, number=%s",
             len(brief["stories"]), len(brief["quick_hits"]),
             brief["number"]["value"] if brief["number"] else "none")
    return brief
