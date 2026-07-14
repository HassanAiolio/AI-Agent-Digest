"""Offline smoke test: no network, mocked items. Run: python pipeline/test_pipeline.py"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yaml

import output
import preferences
from dedupe import SeenDB, canonical_url, dedupe
from models import Item
from scoring import Scorer
from summarize import _fallback, _fallback_detail

CFG = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())


def fake_items() -> list[Item]:
    return [
        # same paper from arXiv and HN — must fuzzy-merge
        Item(title="Scaling Laws for Sparse Mixture of Experts Models",
             url="https://arxiv.org/abs/2607.01234", source="arXiv cs.LG",
             section="ai-ml", abstract="We study MoE scaling with a new benchmark "
             "for inference efficiency and quantization.", weight=1.5),
        Item(title="Scaling laws for sparse mixture-of-experts models",
             url="https://arxiv.org/pdf/2607.01234", source="Hacker News",
             section=None, points=210, weight=1.0),
        # HN item that should route to embedded
        Item(title="Writing a bare-metal bootloader for RISC-V in Rust",
             url="https://example.com/riscv?utm_source=hn", source="Hacker News",
             section=None, points=150, weight=1.0,
             abstract="firmware, microcontroller, bootloader walkthrough"),
        # HN noise that must be dropped (funding news)
        Item(title="AI startup raises $400M Series B at $4B valuation",
             url="https://example.com/funding", source="Hacker News",
             section=None, points=300, weight=1.0),
        # fixed-section blog post
        Item(title="Introducing our new open-weight reasoning model",
             url="https://openai.com/news/new-model", source="openai blog",
             section="ai-ml", weight=3.0,
             abstract="A new LLM with a larger context window."),
        # contest
        Item(title="Upcoming: Codeforces Round 1042 (Div. 2)",
             url="https://codeforces.com/contests/1042", source="Codeforces",
             section="competitive", weight=3.0,
             abstract="CF contest, 2.0h, starts Fri 17 Jul 17:35 UTC"),
    ]


def run():
    assert canonical_url("https://arxiv.org/pdf/2607.01234") == \
           "https://arxiv.org/abs/2607.01234"
    assert "utm_source" not in canonical_url("https://example.com/x?utm_source=hn&a=1")

    tmp = Path(tempfile.mkdtemp())
    db = SeenDB(str(tmp / "seen.sqlite"))
    date1 = "2026-07-14"

    fresh = dedupe(fake_items(), db, date1)
    titles = [i.title for i in fresh]
    assert len([t for t in titles if "calin" in t.lower() or "caling" in t.lower()]) == 1, \
        f"fuzzy merge failed: {titles}"

    buckets = Scorer(CFG).route_and_filter(fresh)
    ai = [i.title for i in buckets["ai-ml"]]
    emb = [i.title for i in buckets["embedded"]]
    allkept = [i.title for b in buckets.values() for i in b]
    assert any("open-weight" in t for t in ai)
    assert any("RISC-V" in t for t in emb), f"routing failed: {emb}"
    assert not any("Series B" in t for t in allkept), "negative filter failed"
    assert any("Codeforces Round" in i.title for i in buckets["competitive"])

    kept = [i for b in buckets.values() for i in b]
    for it in kept:
        it.summary = _fallback(it)
        it.detail = _fallback_detail(it)

    # preferences: a learned tag affinity should reorder a bucket without
    # adding/removing anything (inclusion was already decided by scoring).
    a = Item(title="A", url="https://a", source="src-a", section="x", tag="Research", score=5.0)
    b = Item(title="B", url="https://b", source="src-b", section="x", tag="Release", score=4.0)
    pref_buckets = {"x": [a, b]}
    preferences.apply(pref_buckets, {"tags": {"Release": 3.0}, "sources": {}})
    assert pref_buckets["x"][0].title == "B", "positive tag affinity should outrank a higher raw score"
    assert a.score == 5.0, "unaffected item's score must not change"

    doc = output.write(buckets, CFG, date1, {"fetched": 6}, tmp / "data")
    loaded = json.loads((tmp / "data" / "digest.json").read_text())
    assert loaded["date"] == date1 and loaded["sections"]
    assert (tmp / "data" / "archive" / f"{date1}.json").exists()
    hi_count = int(CFG.get("highlights", {}).get("count", 0))
    assert len(loaded["highlights"]) == min(hi_count, len(kept))

    db.mark(kept, date1)

    # Re-run same night: idempotent, same items survive dedupe.
    fresh2 = dedupe(fake_items(), db, date1)
    b2 = Scorer(CFG).route_and_filter(fresh2)
    assert sum(len(v) for v in b2.values()) == len(kept), "same-night rerun not idempotent"

    # Next night: everything already published is gone.
    fresh3 = dedupe(fake_items(), db, "2026-07-15")
    assert not any(i.id in {k.id for k in kept} for i in fresh3), "seen-DB leak"

    # feedback.json round-trip: dict-keyed-by-id, as /api/feedback writes it
    feedback_path = tmp / "feedback.json"
    feedback_path.write_text(json.dumps({
        "id1": {"vote": 1, "tag": "Release", "source": "openai blog"},
        "id2": {"vote": -1, "tag": "Release", "source": "openai blog"},
        "id3": {"vote": 1, "tag": "Release", "source": "openai blog"},
    }), encoding="utf-8")
    affinity = preferences.load_affinity(feedback_path)
    assert affinity["tags"]["Release"] == 1.0, "net of +1-1+1 votes should be +1"
    assert preferences.load_affinity(tmp / "missing.json") == {"tags": {}, "sources": {}}

    print("ALL PIPELINE TESTS PASSED")
    print(json.dumps(doc, indent=2)[:600])


if __name__ == "__main__":
    run()
