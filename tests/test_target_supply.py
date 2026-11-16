"""Item 82: self-refilling OEIS target supply and new-data retries (fixtures only, no network)."""
from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import colony.target_supply as TS


class FakeNet:
    def __init__(self, budget=40):
        self.n = 0
        self.budget = budget

    def exhausted(self):
        return self.n >= self.budget

    def get(self, url, name):
        self.n += 1
        return "[]"


def _hit(num, name="a(n) = n", text="Conjecture: a(n) = 2*a(n-1)."):
    return {"number": num, "name": name, "data": "1,2,4,8", "offset": "0", "keyword": "nonn",
            "formula": [text]}


class FakeTool:
    TOPICS = ("primes", "sum")
    PAGES = 3

    def __init__(self, pages=None, bad=()):
        self.pages = pages or {}
        self.bad = set(bad)
        self.made = []

    def search_page(self, net, q, page, fn):
        net.n += 1
        return list(self.pages.get((q, page), []))

    def collect_candidates(self, raw, stats):
        return [(0, 1, a, e, "formula", e["formula"][0], None, {"form": "relation"}) for a, e in sorted(raw.items())]

    def make_entry(self, cand, net, per_anum, stats, verbose=True):
        a = cand[2]
        net.n += 1
        if a in self.bad:
            return None
        self.made.append(a)
        return {"id": f"oc_{a}_0", "anum": a, "claim": {"form": "relation"}, "definition": None,
                "terms": [1, 2, 4, 8], "published_hi": 3}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(TS, "SUPPLY_LOG", tmp_path / "target_supply.jsonl")
    monkeypatch.setattr(TS, "STATE_PATH", tmp_path / "target_supply.json")
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    return tmp_path


def test_bank_never_asks_past_the_100_result_window_and_puts_computable_first():
    bank = TS.query_bank(FakeTool())
    assert bank and all(b["page"] < 10 for b in bank)
    kinds = [b["kind"] for b in bank]
    assert kinds.index("plain") > max(i for i, k in enumerate(kinds) if k == "def")
    assert len({b["key"] for b in bank}) == len(bank)


def test_relevance_from_knowledge_library_orders_pages():
    tool = FakeTool()
    bank = TS.query_bank(tool)
    rel = TS.relevance([{"event": "paper", "title": "Lattice walks and Motzkin paths", "summary": "motzkin"}])
    assert rel["motzkin"] == 2
    todo = TS.pending_pages(bank, {"done_pages": {}}, rel)
    assert todo[0]["topic"] == "motzkin"


def test_refill_adds_vetted_new_targets_dedupes_and_logs(paths):
    tool = FakeTool()
    bank = TS.query_bank(tool)
    p0 = bank[0]
    tool.pages[(p0["q"], p0["page"])] = [_hit(1), _hit(2), _hit(3), _hit(4)]
    menu = [{"id": "oc_A000001_0", "anum": "A000001"}]
    heal = {"compute_bound_targets": {"oc_A000002_0": {}}}
    tool.bad = {"A000003"}
    st = TS.load_state()
    rep = TS.refill("c1", net=FakeNet(), tool=tool, menu=menu, st=st, heal=heal, library_rows=[], pages=1)
    assert [e["id"] for e in rep["new"]] == ["oc_A000004_0"]       # 1 on menu, 2 compute_bound, 3 rejected
    assert "A000003" in st["rejected"] and p0["key"] in st["done_pages"]
    rows = TS.load_log()
    assert len(rows) == 1 and rows[0]["event"] == "target_added" and rows[0]["authorized"] is False
    # the next refill reads a different page and never re-adds a rejected anum
    tool.pages[(bank[1]["q"], bank[1]["page"])] = [_hit(3), _hit(5)]
    rep2 = TS.refill("c2", net=FakeNet(), tool=tool, menu=menu + rep["entries"], st=st, heal=heal,
                     library_rows=[], pages=1)
    assert [e["id"] for e in rep2["new"]] == ["oc_A000005_0"]


def test_refill_dry_run_writes_nothing(paths):
    tool = FakeTool()
    p0 = TS.query_bank(tool)[0]
    tool.pages[(p0["q"], p0["page"])] = [_hit(7)]
    rep = TS.refill("c", net=FakeNet(), tool=tool, menu=[], st=TS.load_state(), library_rows=[],
                    pages=1, write=False)
    assert rep["new"] and not TS.SUPPLY_LOG.exists() and not TS.STATE_PATH.exists()


def test_failed_fetch_leaves_page_for_later(paths, monkeypatch):
    tool = FakeTool()
    monkeypatch.setattr(TS, "_cached", lambda name: False)
    st = TS.load_state()
    rep = TS.refill("c", net=FakeNet(), tool=tool, menu=[], st=st, library_rows=[], pages=3)
    assert rep["pages_read"] == 0 and not st["done_pages"]


def test_budget_stops_refill(paths):
    tool = FakeTool()
    p0 = TS.query_bank(tool)[0]
    tool.pages[(p0["q"], p0["page"])] = [_hit(i) for i in range(10, 20)]
    rep = TS.refill("c", net=FakeNet(budget=3), tool=tool, menu=[], st=TS.load_state(), library_rows=[], pages=1)
    assert len(rep["new"]) <= 2


def _fake_oc(tmp_path, entries):
    menu = tmp_path / "oeis_conjectures.json"
    menu.write_text(json.dumps({"note": "x", "stats": {}, "entries": entries}))
    return types.SimpleNamespace(MENU=menu)


def test_sync_adds_only_earlier_runs_and_menu_only_grows(paths, tmp_path):
    oc = _fake_oc(tmp_path, [{"id": "oc_A000001_0", "anum": "A000001"}])
    rows = [{"event": "target_added", "run_id": "41", "entry": {"id": "oc_A000009_0", "anum": "A000009"}},
            {"event": "target_added", "run_id": "42", "entry": {"id": "oc_A000010_0", "anum": "A000010"}},
            {"event": "target_added", "run_id": "40", "entry": {"id": "oc_A000001_0", "anum": "A000001"}}]
    out = TS.sync(oc=oc, rows=rows, run_id="42")
    assert out["added"] == ["oc_A000009_0"]
    doc = json.loads(oc.MENU.read_text())
    assert [e["id"] for e in doc["entries"]] == ["oc_A000001_0", "oc_A000009_0"]
    assert doc["stats"]["supply_added"] == 1
    # the next run adopts run 42's target too; nothing is ever removed
    assert TS.sync(oc=oc, rows=rows, run_id="43")["added"] == ["oc_A000010_0"]


def test_both_arms_adopt_identical_supply(paths, tmp_path):
    rows = [{"event": "target_added", "run_id": "7", "entry": {"id": f"oc_A00000{i}_0", "anum": f"A00000{i}"}}
            for i in range(1, 4)]
    (tmp_path / "t").mkdir()
    (tmp_path / "c").mkdir()
    t = _fake_oc(tmp_path / "t", [])
    c = _fake_oc(tmp_path / "c", [])
    TS.sync(oc=t, rows=rows, run_id="8")
    TS.sync(oc=c, rows=rows, run_id="8")
    assert json.loads(t.MENU.read_text())["entries"] == json.loads(c.MENU.read_text())["entries"]


def test_control_arm_never_refills(paths, monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    monkeypatch.setenv("COLONY_OEIS_CONJ", "live")
    called = []
    monkeypatch.setattr(TS, "refill", lambda *a, **k: called.append(1) or {})
    monkeypatch.setattr(TS, "sync", lambda **k: {"added": []})
    out = TS.run_cycle("c")
    assert out["arm"] == "control" and not called and "refill" not in out


def test_treatment_refills_when_low_with_cooldown(paths, monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_OEIS_CONJ", "live")
    calls = []
    monkeypatch.setattr(TS, "refill", lambda cid, **k: calls.append(cid) or {"new": [{"id": "x"}], "pages_read": 1})
    monkeypatch.setattr(TS, "sync", lambda **k: {"added": []})
    monkeypatch.setattr(TS, "open_count", lambda cid="": 0)
    monkeypatch.setattr(TS, "_heal", lambda: {})
    for i in range(4):
        TS.run_cycle(f"c{i}")
    assert calls == ["c0", "c3"]
    st = TS.load_state()
    assert st["refills"] == 2 and st["added"] == 2
    monkeypatch.setattr(TS, "open_count", lambda cid="": TS.OPEN_MIN)
    TS.run_cycle("c9")
    assert calls == ["c0", "c3"]


def test_society_runs_supply_before_frontier():
    import inspect
    import colony.society as S
    src = inspect.getsource(S.Society.run_cycle)
    assert src.index('"target_supply"') < src.index('self._stage(result, "frontier", frontier_stage)')


def test_tool_is_importable_and_exposes_vetting_steps():
    tool = TS._tool()
    for name in ("collect_candidates", "make_entry", "search_page", "bfile", "verified_definition"):
        assert callable(getattr(tool, name))


def test_new_data_retries_unknown_after_a_day_and_index_misses_after_a_month():
    from colony import new_data as N
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    ts = lambda d: (now - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    assert N.retryable({"status": N.LABEL_UNKNOWN, "ts": ts(2)}, now)
    assert not N.retryable({"status": N.LABEL_UNKNOWN, "ts": ts(0)}, now)
    assert N.retryable({"status": "not_in_oeis", "ts": ts(31)}, now)
    assert not N.retryable({"status": "not_in_oeis", "ts": ts(5)}, now)
    assert not N.retryable({"status": "matched", "ts": ts(90)}, now)
    assert not N.retryable({"status": "too_short", "ts": ts(90)}, now)


def test_refactored_builder_vets_a_fixture_hit_offline():
    """The builder's unchanged vetting, now callable per candidate (b-file from a fake net)."""
    tool = TS._tool()

    class BNet:
        n = 0

        def get(self, url, name):
            self.n += 1
            return "\n".join(f"{i} {2 ** i}" for i in range(60))

    good = {"number": 79, "name": "Powers of 2.", "data": ",".join(str(2 ** i) for i in range(30)),
            "offset": "0", "keyword": "nonn", "formula": ["Conjecture: a(n) = 2*a(n-1)."]}
    wrong = dict(good, number=80, formula=["Conjecture: a(n) = 3*a(n-1)."])
    solved = dict(good, number=81, comment=["This conjecture was proved by X."])
    stats = {"entries": 3, "resolved_skipped": 0, "keyword_skipped": 0, "statements": 0, "parsed": 0,
             "no_bfile": 0, "fails_on_data": 0, "kept": 0, "reasons": {}}
    cands = tool.collect_candidates({"A000079": good, "A000080": wrong, "A000081": solved}, stats)
    made = [tool.make_entry(c, BNet(), {}, stats, verbose=False) for c in cands]
    kept = [m["anum"] for m in made if m]
    assert kept == ["A000079"]
    assert stats["fails_on_data"] == 1


def test_added_targets_store_a_bounded_prefix_but_keep_published_range():
    ent = {"id": "oc_A1_0", "anum": "A1", "offset": 0, "terms": list(range(3000)), "published_hi": 2999,
           "refs": {"A2": {"offset": 0, "terms": list(range(3000))}}}
    out = TS._trim(ent)
    assert len(out["terms"]) == TS.SUPPLY_MAX_TERMS and out["published_hi"] == 2999
    assert len(out["refs"]["A2"]["terms"]) == TS.SUPPLY_MAX_TERMS + 12
    from colony.oeis_conjectures import bfile_hi_of
    assert bfile_hi_of(out) == 2999
