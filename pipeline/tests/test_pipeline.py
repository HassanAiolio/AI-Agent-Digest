"""End-to-end over mocked items: dedupe → score → preferences → output."""
import json
import sqlite3

import output
import preferences
from dedupe import SeenDB, canonical_url, dedupe
from models import Item
from scoring import Scorer
from summarize import _fallback, _fallback_detail


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
        # two contests with near-identical names: evergreen, never merged
        Item(title="Codeforces Round 1042 (Div. 2)",
             url="https://codeforces.com/contests/1042", source="Codeforces",
             section="competitive", weight=3.0, evergreen=True,
             published="2026-07-17T17:35:00+00:00",
             abstract="CF contest, 2.0h, starts Fri 17 Jul 17:35 UTC"),
        Item(title="Codeforces Round 1043 (Div. 2)",
             url="https://codeforces.com/contests/1043", source="Codeforces",
             section="competitive", weight=3.0, evergreen=True,
             published="2026-07-19T17:35:00+00:00",
             abstract="CF contest, 2.0h, starts Sun 19 Jul 17:35 UTC"),
    ]


def test_canonical_url():
    assert canonical_url("https://arxiv.org/pdf/2607.01234") == "https://arxiv.org/abs/2607.01234"
    assert "utm_source" not in canonical_url("https://example.com/x?utm_source=hn&a=1")


def test_full_run(tmp_path, cfg):
    db = SeenDB(str(tmp_path / "seen.json"))
    date1 = "2026-07-14"

    fresh = dedupe(fake_items(), db, date1)
    titles = [i.title for i in fresh]
    assert len([t for t in titles if "caling" in t.lower()]) == 1, f"fuzzy merge failed: {titles}"
    assert sum("Codeforces Round" in t for t in titles) == 2, "distinct contests must not merge"

    upcoming = [i for i in fresh if i.evergreen]
    buckets = Scorer(cfg).route_and_filter([i for i in fresh if not i.evergreen])
    ai = [i.title for i in buckets["ai-ml"]]
    emb = [i.title for i in buckets["embedded"]]
    allkept = [i.title for b in buckets.values() for i in b]
    assert any("open-weight" in t for t in ai)
    assert any("RISC-V" in t for t in emb), f"routing failed: {emb}"
    assert not any("Series B" in t for t in allkept), "negative filter failed"

    kept = [i for b in buckets.values() for i in b]
    for it in kept:
        it.summary = _fallback(it)
        it.detail = _fallback_detail(it)

    doc = output.write(buckets, cfg, date1, {"fetched": 7}, tmp_path / "data", upcoming=upcoming)
    loaded = json.loads((tmp_path / "data" / "digest.json").read_text(encoding="utf-8"))
    assert loaded["date"] == date1 and loaded["sections"]
    assert (tmp_path / "data" / "archive" / f"{date1}.json").exists()
    assert len(loaded["highlights"]) == min(int(cfg["highlights"]["count"]), len(kept))
    assert [u["title"] for u in loaded["upcoming"]] == ["Codeforces Round 1042 (Div. 2)",
                                                        "Codeforces Round 1043 (Div. 2)"]
    assert "abstract" not in loaded["sections"][0]["items"][0]
    assert doc["brief"] is None

    db.mark(kept, date1)
    db.save()

    # Re-run same night: idempotent, same items survive dedupe.
    db = SeenDB(str(tmp_path / "seen.json"))
    fresh2 = dedupe(fake_items(), db, date1)
    b2 = Scorer(cfg).route_and_filter([i for i in fresh2 if not i.evergreen])
    assert sum(len(v) for v in b2.values()) == len(kept), "same-night rerun not idempotent"

    # Next night: everything already published is gone — except contests.
    fresh3 = dedupe(fake_items(), db, "2026-07-15")
    kept_ids = {k.id for k in kept}
    assert not any(i.id in kept_ids for i in fresh3), "seen-DB leak"
    assert sum(i.evergreen for i in fresh3) == 2, "upcoming contests must repeat nightly"


def test_seen_db_migrates_from_sqlite(tmp_path):
    legacy = tmp_path / "seen.sqlite"
    conn = sqlite3.connect(legacy)
    conn.execute("CREATE TABLE seen (id TEXT PRIMARY KEY, url TEXT, title TEXT, digest_date TEXT)")
    conn.execute("INSERT INTO seen VALUES ('abc', 'https://x', 'X', '2026-07-01')")
    conn.commit()
    conn.close()

    db = SeenDB(str(tmp_path / "seen.json"))
    assert db.published_date("abc") == "2026-07-01"
    assert db.prune("2026-06-01") == 0
    db.save()
    assert not legacy.exists(), "legacy sqlite should be removed once migrated"
    assert json.loads((tmp_path / "seen.json").read_text())["abc"]["title"] == "X"


def test_preferences_reorder_without_filtering():
    a = Item(title="A", url="https://a", source="src-a", section="x", tag="Research", score=5.0, id="a")
    b = Item(title="B", url="https://b", source="src-b", section="x", tag="Release", score=4.0, id="b")
    buckets = {"x": [a, b]}
    preferences.apply(buckets, {"tags": {"Release": 3.0}, "sources": {}})
    assert buckets["x"][0].title == "B", "positive tag affinity should outrank a higher raw score"
    assert a.score == 5.0, "unaffected item's score must not change"

    # semantic taste boost stacks with tag/source affinity
    preferences.apply(buckets, {"tags": {}, "sources": {}}, {"a": 4.0})
    assert buckets["x"][0].title == "A"
    assert len(buckets["x"]) == 2


def test_feedback_affinity(tmp_path):
    path = tmp_path / "feedback.json"
    path.write_text(json.dumps({
        "id1": {"vote": 1, "tag": "Release", "source": "openai blog"},
        "id2": {"vote": -1, "tag": "Release", "source": "openai blog"},
        "id3": {"vote": 1, "tag": "Release", "source": "openai blog"},
    }), encoding="utf-8")
    assert preferences.load_affinity(path)["tags"]["Release"] == 1.0
    assert preferences.load_affinity(tmp_path / "missing.json") == {"tags": {}, "sources": {}}
    assert preferences.load_raw(tmp_path / "missing.json") == {}
    assert len(preferences.load_raw(path)) == 3
