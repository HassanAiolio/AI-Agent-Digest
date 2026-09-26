"""The weekly recap: one Sunday issue that reads the last seven editions and
says what the week was actually about.

Nightly items are one-offs; the interesting signal is what kept coming
back. The recap groups the week's strongest items into 3-4 themes, pulls a
few numbers of the week, and names one thing to watch. Same rules as the
brief: only facts from the archived items, every theme cites item ids, and
cited ids are resolved to title/url/date here so the page is self-contained.

Writes data/weekly/<ISO week>.json, e.g. data/weekly/2026-W39.json.
Run automatically by main.py on the configured weekday, or by hand:
    python pipeline/weekly.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import brief
import llm

log = logging.getLogger("weekly")

PROMPT = """You write the Sunday "week in review" issue of a tech \
newsletter in the style of Morning Brew: smart, conversational, a little \
witty, never hype. Readers are software engineers into AI/ML, embedded \
systems, competitive programming and CS research.

Below are the strongest items from the last seven nightly editions. Find \
what the week was actually about: themes that recur across several days, \
not just the single biggest item. Use ONLY facts from these items.

Produce a JSON object with exactly these keys:
- "title": a punchy issue title, max 8 words.
- "intro": 2 sentences (max 45 words) setting up the week.
- "themes": 3-4 objects, each {{"headline": max 8 words, "body": 3-4 \
sentences (max 90 words) that connect the items, starting with a \
**bolded lead-in:**, "ids": array of 2+ item ids it draws on}}.
- "numbers": 2-3 objects {{"value": max 8 chars, "label": max 14 words, \
"id": item id}} — striking figures that appear in the items' text.
- "watch": one sentence (max 30 words) on what to keep an eye on next week, \
grounded in the items.

Respond with ONLY the JSON object.

Items:
{items}"""


def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _load_week(archive_dir: Path, end: date) -> list[dict]:
    items = []
    for n in range(7):
        d = (end - timedelta(days=n)).isoformat()
        f = archive_dir / f"{d}.json"
        if not f.exists():
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        for s in doc.get("sections", []):
            for it in s.get("items", []):
                items.append({**it, "date": d, "section_title": s.get("title", "")})
    return items


def _pick(items: list[dict], limit: int) -> list[dict]:
    """Highlights and brief-cited items first, then by score, capped per
    section so one busy section can't take the whole week."""
    ranked = sorted(items, key=lambda i: (not i.get("highlight"), -i.get("score", 0)))
    per_section: dict[str, int] = {}
    out = []
    for it in ranked:
        sec = it.get("section", "")
        if per_section.get(sec, 0) >= max(4, limit // 3):
            continue
        per_section[sec] = per_section.get(sec, 0) + 1
        out.append(it)
        if len(out) >= limit:
            break
    return out


def _clean(text, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    text = brief._LITERAL_LEAD.sub("", " ".join(text.split()))
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _ref(it: dict) -> dict:
    return {"id": it["id"], "title": it["title"], "url": it["url"], "date": it["date"],
            "source": it.get("source", ""), "section": it.get("section_title", "")}


def build(data_dir: Path, gcfg: dict, end: date, limit: int = 30) -> dict | None:
    week_items = _load_week(data_dir / "archive", end)
    picked = _pick(week_items, limit)
    if len(picked) < 6:
        log.info("weekly: only %d items this week — skipping", len(picked))
        return None
    if not llm.available():
        log.warning("weekly: GROQ_API_KEY not set — skipping")
        return None

    by_id = {it["id"]: it for it in picked}
    lines = "\n\n".join(
        f"id: {it['id']}\ndate: {it['date']}\nsection: {it['section_title']}\n"
        f"title: {it['title']}\nsummary: {it.get('summary', '')}"
        + (f"\nfacts: {'; '.join(it.get('key_points') or [])}" if it.get("key_points") else "")
        for it in picked
    )
    try:
        data = llm.chat_json(PROMPT.format(items=lines), gcfg, max_tokens=2600)
    except llm.LLMError as e:
        log.warning("weekly LLM call failed: %s", e)
        return None

    themes = []
    for t in data.get("themes") or []:
        if not isinstance(t, dict):
            continue
        ids = [i for i in (t.get("ids") or []) if i in by_id]
        headline, body = _clean(t.get("headline"), 90), _clean(t.get("body"), 700)
        if ids and headline and body:
            themes.append({"headline": headline, "body": body, "items": [_ref(by_id[i]) for i in ids[:5]]})
    if len(themes) < 2:
        log.warning("weekly: model returned %d usable themes — skipping", len(themes))
        return None

    numbers = []
    for n in data.get("numbers") or []:
        if isinstance(n, dict) and n.get("id") in by_id:
            it = by_id[n["id"]]
            value = _clean(n.get("value"), 12)
            text = f"{it['title']} {it.get('summary', '')} {' '.join(it.get('key_points') or [])}".replace(",", "")
            digits = re.findall(r"\d+(?:\.\d+)?", value.replace(",", ""))
            if value and digits and all(d in text for d in digits):
                numbers.append({"value": value, "label": _clean(n.get("label"), 110), "item": _ref(it)})

    start = end - timedelta(days=6)
    return {
        "week": iso_week(end),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "title": _clean(data.get("title"), 80) or f"Week {iso_week(end)}",
        "intro": _clean(data.get("intro"), 320),
        "themes": themes[:4],
        "numbers": numbers[:3],
        "watch": _clean(data.get("watch"), 240),
        "item_count": len(week_items),
    }


def write(doc: dict, data_dir: Path) -> Path:
    out_dir = data_dir / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{doc['week']}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    import yaml
    logging.basicConfig(level=logging.INFO, format="%(name)-10s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="last day of the week (default: today)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))
    end = date.fromisoformat(args.date) if args.date else date.today()
    doc = build(root / "data", cfg["groq"], end)
    if doc:
        log.info("wrote %s", write(doc, root / "data"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
