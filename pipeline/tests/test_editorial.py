"""LLM-facing stages: faithfulness check, brief validation, weekly recap,
rate-limit parsing. No network: the LLM call itself is monkeypatched."""
import json
from datetime import date

import brief
import llm
import semantic
import summarize
import verify
import weekly
from models import Item
from summarize import _fallback


def item(id_, title, abstract="", summary="", key_points=None, section="ai-ml", score=1.0):
    return Item(title=title, url=f"https://x/{id_}", source="src", section=section,
                abstract=abstract, summary=summary, key_points=key_points or [],
                id=id_, score=score)


# ---- verify ----

def test_verify_drops_invented_numbers_keeps_supported():
    it = item("a", "New 70B model", abstract="A 70B parameter model trained on 2,048 GPUs. MIT license.",
              summary="A 70B model trained on 2048 GPUs.",
              key_points=["70B parameters", "2048 GPUs", "Scores 91.3 on MMLU", "MIT license"])
    stats = verify.check({"ai-ml": [it]}, _fallback)
    assert it.key_points == ["70B parameters", "2048 GPUs", "MIT license"]
    assert it.summary == "A 70B model trained on 2048 GPUs."
    assert stats["dropped"] == 1 and stats["unverifiable"] == 1
    assert stats["supported"] == 3 and stats["checked"] == 4
    assert stats["rate"] == 0.75


def test_verify_reverts_summary_with_invented_number():
    it = item("a", "Some release", abstract="Faster inference for small models.",
              summary="Makes inference 40% faster.")
    stats = verify.check({"x": [it]}, _fallback)
    assert it.summary == "Faster inference for small models."
    assert stats["summaries_reverted"] == 1


def test_verify_single_digits_are_not_checked():
    it = item("a", "t", abstract="text", key_points=["3 new models"])
    stats = verify.check({"x": [it]}, _fallback)
    assert it.key_points == ["3 new models"] and stats["checked"] == 0 and stats["rate"] is None


# ---- brief ----

def _buckets():
    items = [item(f"id{i}", f"Title {i}", abstract=f"Abstract {i} with 12{i} tokens",
                  summary=f"Summary {i}.", score=10 - i) for i in range(6)]
    items[0].highlight = items[1].highlight = True
    return {"ai-ml": items[:4], "embedded": [Item(**{**items[4].__dict__, "section": "embedded"})],
            "repos": [Item(**{**items[5].__dict__, "section": "repos"})]}


def test_brief_candidates_span_sections():
    picked = brief._candidates(_buckets(), 5)
    assert [p.id for p in picked[:2]] == ["id0", "id1"], "highlights lead"
    assert {"embedded", "repos"} <= {p.section for p in picked}


def test_brief_validation_drops_unknown_ids_and_unsupported_number(monkeypatch, cfg):
    reply = {
        "greeting": "Good morning. Busy night.",
        "stories": [
            {"kicker": "AI", "headline": "One", "body": "**Lead:** body", "why": "w", "ids": ["id0"]},
            {"kicker": "AI", "headline": "Two", "body": "**Lead:** body", "why": "w", "ids": ["nope", "id1"]},
            {"kicker": "AI", "headline": "Ghost", "body": "b", "why": "w", "ids": ["nope"]},
        ],
        "quick_hits": [{"text": "hit", "id": "id2"}, {"text": "dup of story", "id": "id0"},
                       {"text": "ghost", "id": "zzz"}],
        "number": {"value": "999", "label": "invented", "id": "id2"},
        "sign_off": "See you tomorrow.",
    }
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: reply)
    b = brief.build(_buckets(), cfg, use_llm=True)
    assert b["generated"] == "llm"
    assert [s["headline"] for s in b["stories"]] == ["One", "Two"]
    assert b["stories"][1]["ids"] == ["id1"]
    assert [h["id"] for h in b["quick_hits"]] == ["id2"]
    assert b["number"] is None, "a number not in the item's text must be dropped"

    reply["number"] = {"value": "122", "label": "tokens", "id": "id2"}
    assert brief.build(_buckets(), cfg, use_llm=True)["number"]["value"] == "122"


def test_brief_falls_back_without_llm(cfg):
    b = brief.build(_buckets(), cfg, use_llm=False)
    assert b["generated"] == "fallback" and len(b["stories"]) == 3
    assert b["stories"][0]["ids"] == ["id0"]


def test_brief_falls_back_on_llm_error(monkeypatch, cfg):
    monkeypatch.setenv("GROQ_API_KEY", "test")

    def boom(*a, **k):
        raise llm.LLMError("429")
    monkeypatch.setattr(llm, "chat_json", boom)
    assert brief.build(_buckets(), cfg, use_llm=True)["generated"] == "fallback"


# ---- summarize ----

def test_summarize_batches_and_parses(monkeypatch, cfg):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    calls = []

    def fake(prompt, gcfg, max_tokens):
        ids = [line[4:] for line in prompt.splitlines() if line.startswith("id: ")]
        calls.append((len(ids), max_tokens))
        return {"items": [{"id": i, "summary": f"S {i}", "key_points": ["k", 3], "detail": "D",
                           "tag": "Release" if n == 0 else "Bogus"} for n, i in enumerate(ids)]}
    monkeypatch.setattr(llm, "chat_json", fake)
    items = [item(f"i{n}", f"T{n}", abstract="a") for n in range(8)]
    assert summarize.summarize_all({"x": items}, cfg["groq"]) is True
    assert [c[0] for c in calls] == [6, 2]
    assert calls[0][1] == 6 * 320 + 300
    assert items[0].tag == "Release" and items[1].tag == "", "unknown tags are dropped"
    assert items[0].key_points == ["k"]


# ---- weekly ----

def test_weekly_recap_resolves_items(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    for d in ("2026-09-21", "2026-09-24", "2026-09-27"):
        doc = {"sections": [{"id": "ai-ml", "title": "AI & ML", "items": [
            {"id": f"{d}-{n}", "title": f"Item {d} {n}", "url": f"https://x/{d}/{n}",
             "summary": "Uses 64 GPUs", "key_points": [], "score": n, "source": "s",
             "section": "ai-ml", "highlight": n == 0} for n in range(3)]}]}
        (archive / f"{d}.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {
        "title": "Big week", "intro": "Intro.",
        "themes": [{"headline": "H1", "body": "B1", "ids": ["2026-09-21-0", "2026-09-24-1"]},
                   {"headline": "H2", "body": "B2", "ids": ["2026-09-27-2"]},
                   {"headline": "Ghost", "body": "B", "ids": ["nope"]}],
        "numbers": [{"value": "64", "label": "GPUs", "id": "2026-09-24-0"},
                    {"value": "1M", "label": "made up", "id": "2026-09-24-0"}],
        "watch": "Watch this.",
    })
    doc = weekly.build(tmp_path, {}, date(2026, 9, 27))
    assert doc["week"] == "2026-W39" and doc["start"] == "2026-09-21"
    assert [t["headline"] for t in doc["themes"]] == ["H1", "H2"]
    assert doc["themes"][0]["items"][1]["date"] == "2026-09-24"
    assert [n["value"] for n in doc["numbers"]] == ["64"]
    path = weekly.write(doc, tmp_path)
    assert path.name == "2026-W39.json"


# ---- llm helpers ----

def test_duration_parsing():
    assert llm._duration("7.66s") == 7.66
    assert llm._duration("2m59.5s") == 179.5
    assert llm._duration("120ms") == 0.12
    assert llm._duration("30") == 30.0
    assert llm._duration(None) is None


def test_budget_waits_only_when_request_would_not_fit(monkeypatch):
    slept = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    b = llm._Budget()
    b.update({"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-reset-tokens": "10s"})
    b.wait_for(3000)
    assert slept == []
    b.wait_for(9000)
    assert len(slept) == 1 and 0 < slept[0] <= 10


def test_semantic_is_a_noop_without_model(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic, "_embedder", lambda: None)
    items = [item("a", "x"), item("b", "y")]
    assert semantic.dedupe(items, lambda i: 0) == items
    assert semantic.attach_related({"x": items}, tmp_path, "2026-09-26") == 0
    assert semantic.taste_boost({"x": items}, {"a": {"vote": 1, "title": "x"}}) == {}


def test_truncated_json_is_retried_with_bigger_budget(monkeypatch):
    budgets = []

    class Resp:
        def __init__(self, ok):
            self.ok = ok
            self.status_code = 200 if ok else 400
            self.headers = {}
            self.text = "" if ok else '{"error":{"code":"json_validate_failed"}}'

        def raise_for_status(self):
            if not self.ok:
                raise llm.requests.HTTPError("400 Bad Request")

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    def post(url, headers, json, timeout):
        budgets.append(json["max_tokens"])
        assert json["reasoning_effort"] == "low"
        return Resp(ok=len(budgets) > 1)

    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm.chat_json("p", {"model": "openai/gpt-oss-120b"}, max_tokens=1000) == {"ok": True}
    assert budgets == [1000, 1600]
