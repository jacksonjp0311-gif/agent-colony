"""Item 121: bank-v2 supply pace, item-121 NAME grammar (Sum ranges, C(), referenced b-files),
and the PERTURB -> supply route. Fixtures only, no network."""
from __future__ import annotations

import json
import math

import pytest

import colony.target_supply as TS
from colony import oeis_definitions as OD
from colony import stall as S


class FakeNet:
    def __init__(self, budget=40):
        self.n = 0
        self.budget = budget

    def exhausted(self):
        return self.n >= self.budget

    def get(self, url, name):
        self.n += 1
        return "[]"


def _hit(num):
    return {"number": num, "name": "a(n) = n", "data": "1,2,4,8", "offset": "0", "keyword": "nonn",
            "formula": ["Conjecture: a(n) = 2*a(n-1)."]}


class FakeTool:
    TOPICS = ("primes",)
    PAGES = 3

    def __init__(self):
        self.pages = {}
        self.searched = []

    def search_page(self, net, q, page, fn):
        net.n += 1
        self.searched.append((q, page))
        return list(self.pages.get((q, page), []))

    def collect_candidates(self, raw, stats):
        return [(1, 1, a, e, "formula", e["formula"][0], None, {"form": "relation"}) for a, e in sorted(raw.items())]

    def make_entry(self, cand, net, per_anum, stats, verbose=True):
        net.n += 1
        a = cand[2]
        return {"id": f"oc_{a}_0", "anum": a, "claim": {"form": "relation"}, "definition": None,
                "terms": [1, 2, 4, 8], "published_hi": 3}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(TS, "SUPPLY_LOG", tmp_path / "target_supply.jsonl")
    monkeypatch.setattr(TS, "STATE_PATH", tmp_path / "target_supply.json")
    monkeypatch.setattr(TS, "_cached", lambda name: True)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("COLONY_SUPPLY_PACE", raising=False)
    return tmp_path


def _two_page_query(bank):
    p0 = next(b for b in bank if b["page"] == 0)
    p1 = next(b for b in bank if b["q"] == p0["q"] and b["page"] == 1)
    return p0, p1


def test_page_after_a_short_page_is_skipped_without_a_request(paths):
    tool = FakeTool()
    bank = TS.query_bank(tool)
    p0, p1 = _two_page_query(bank)
    tool.pages[(p0["q"], 0)] = [_hit(1), _hit(2), _hit(3)]          # short: page 1 would repeat it
    st = TS.load_state()
    rep = TS.refill("c", net=FakeNet(), tool=tool, menu=[], st=st, library_rows=[], pages=2)
    assert st["done_pages"][p1["key"]]["skipped"] == "duplicate_after_short_page"
    assert (p1["q"], 1) not in tool.searched
    assert rep["pages_skipped_duplicate"] >= 1 and rep["pages_read"] == 2   # skip did not use the allowance


def test_full_page_keeps_its_next_page(paths):
    tool = FakeTool()
    bank = TS.query_bank(tool)
    p0, p1 = _two_page_query(bank)
    tool.pages[(p0["q"], 0)] = [_hit(i) for i in range(1, 11)]       # 10 hits: page 1 may hold more
    st = TS.load_state()
    TS.refill("c", net=FakeNet(budget=10 ** 6), tool=tool, menu=[], st=st, library_rows=[], pages=2,
              max_new=10 ** 6)
    assert (p1["q"], 1) in tool.searched
    assert "skipped" not in st["done_pages"][p1["key"]]


def test_no_hit_is_lost_past_max_new(paths):
    tool = FakeTool()
    bank = TS.query_bank(tool)
    p0 = bank[0]
    later = next(b for b in bank[1:] if b["page"] == 0)
    tool.pages[(p0["q"], p0["page"])] = [_hit(i) for i in range(1, 11)]
    tool.pages[(later["q"], 0)] = [_hit(i) for i in range(50, 55)]
    st = TS.load_state()
    rep = TS.refill("c", net=FakeNet(budget=10 ** 6), tool=tool, menu=[], st=st, library_rows=[],
                    pages=8, max_new=4)
    assert len(rep["new"]) == 10            # the whole page is vetted, not cut at max_new
    assert later["key"] not in st["done_pages"]   # and no further page is marked read


def test_budget_cut_mid_page_leaves_page_unread(paths):
    tool = FakeTool()
    p0 = TS.query_bank(tool)[0]
    tool.pages[(p0["q"], p0["page"])] = [_hit(i) for i in range(1, 11)]
    st = TS.load_state()
    rep = TS.refill("c", net=FakeNet(budget=4), tool=tool, menu=[], st=st, library_rows=[], pages=1)
    assert p0["key"] not in st["done_pages"] and len(rep["new"]) == 3
    # the retry dedupes what was already logged
    rep2 = TS.refill("c2", net=FakeNet(budget=10 ** 6), tool=tool, menu=[], st=st, library_rows=[], pages=1)
    assert {e["id"] for e in rep2["new"]}.isdisjoint({e["id"] for e in rep["new"]})
    assert p0["key"] in st["done_pages"]


def test_pace_off_is_the_old_refill(paths, monkeypatch):
    monkeypatch.setenv("COLONY_SUPPLY_PACE", "off")
    tool = FakeTool()
    bank = TS.query_bank(tool)
    p0, p1 = _two_page_query(bank)
    tool.pages[(p0["q"], 0)] = [_hit(i) for i in range(1, 8)]
    st = TS.load_state()
    rep = TS.refill("c", net=FakeNet(), tool=tool, menu=[], st=st, library_rows=[], pages=2, max_new=3)
    assert (p1["q"], 1) in tool.searched and len(rep["new"]) == 3   # old: reads the duplicate, cuts at max_new
    assert TS.refill_size(0) == (TS.PAGES_PER_REFILL, TS.REQUEST_BUDGET)


def test_refill_size_starved_and_run_cap(paths, monkeypatch):
    assert TS.refill_size(3) == (TS.PAGES_PER_REFILL, TS.REQUEST_BUDGET)
    assert TS.refill_size(0) == (TS.STARVED_PAGES, TS.STARVED_REQUEST_BUDGET)
    monkeypatch.setenv("GITHUB_RUN_ID", "77")
    st = {"run_requests": {"run_id": "77", "n": TS.RUN_REQUEST_CAP - 5}}
    assert TS.refill_size(0, st)[1] == 5
    TS.note_run_requests(st, 5)
    assert TS.refill_size(0, st)[1] == 0
    assert TS.refill_size(0, {"run_requests": {"run_id": "76", "n": 999}})[1] == TS.STARVED_REQUEST_BUDGET


# ----------------------------------------------------------------------------- definitions

def test_sum_range_equals_sign_no_longer_rejects_the_name(monkeypatch):
    txt = "a(n) = Sum_{k=0..n} binomial(n,k)*binomial(2*n+k-1,k)."
    d = OD._xexpr_from(txt)
    assert d is not None
    terms = [sum(math.comb(n, k) * math.comb(2 * n + k - 1, k) for k in range(n + 1)) if n else 1
             for n in range(0, 60)]
    assert OD.reproduces(d, 0, terms)[0]
    assert OD._xexpr_from("a(n) = n + 1 = m") is None            # a real chained equality still is
    monkeypatch.setenv("COLONY_OEIS_DEF_WIDEN2", "off")
    assert OD._xexpr_from(txt) is None                           # old behaviour behind the switch


def test_c_alias_is_binomial():
    d = OD._xexpr_from("a(n) = Sum_{k = 0..n} C(n,k) * C(n+k,k).")
    terms = [sum(math.comb(n, k) * math.comb(n + k, k) for k in range(n + 1)) for n in range(50)]
    assert d and OD.reproduces(d, 0, terms)[0]


def _ref_row(off, vals):
    vals = list(vals)
    return {"offset": off, "terms": vals, "published_hi": off + len(vals) - 1}


def test_referenced_bfile_definition_and_ref_cap():
    ref = [math.comb(2 * k, k) for k in range(80)]                   # stands in for a published b-file
    e = {"id": "oc_A999999_0", "anum": "A999999", "offset": 0,
         "name": "a(n) = Sum_{k=0..n} binomial(n,k)*A123456(k).",
         "terms": [sum(math.comb(n, k) * ref[k] for k in range(n + 1)) for n in range(60)]}
    d, tried = OD.find_definition(e, cache={"entries": {}}, seconds=5, use_guess=False,
                                  ref_loader=lambda a: _ref_row(0, ref) if a == "A123456" else None)
    assert d and d["provenance"] == "name" and d["sound"] and d["refs_used"] == ["A123456"]
    got, cap = OD.extend_widened(d, 0, e["terms"], 200, "A", 5.0, 10 ** 6)
    assert cap == "ref_cap" and len(got) == 80                       # stops at the end of the referenced b-file
    gotB, capB = OD.extend_widened(d, 0, e["terms"], 200, "B", 5.0, 10 ** 6)
    assert gotB == got and capB == "ref_cap"


def test_referenced_definition_refused_when_missing_or_self():
    e = {"id": "oc_A123456_0", "anum": "A123456", "offset": 0,
         "name": "a(n) = Sum_{k=0..n} A123456(k).", "terms": list(range(40))}
    d, tried = OD.find_definition(e, cache={"entries": {}}, seconds=2, use_guess=False,
                                  ref_loader=lambda a: _ref_row(0, range(40)))
    assert d is None and "own A-number" in tried[0]["why"]
    e2 = dict(e, anum="A000001", id="oc_A000001_0")
    d2, tried2 = OD.find_definition(e2, cache={"entries": {}}, seconds=2, use_guess=False,
                                    ref_loader=lambda a: None)
    assert d2 is None and "unavailable" in tried2[0]["why"]


def test_table_version_tracks_the_switch(monkeypatch):
    assert OD.table_version() == OD.VERSION_WIDEN2
    monkeypatch.setenv("COLONY_OEIS_DEF_WIDEN2", "off")
    assert OD.table_version() == OD.VERSION


def test_definitions_stay_off_on_control(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert OD.enabled() is False and OD.definition_for({"id": "x"}) is None


# ----------------------------------------------------------------------------- perturb -> supply

def test_supply_route_opt_in_under_tests_and_off_on_control(monkeypatch):
    monkeypatch.delenv("COLONY_PERTURB_SUPPLY_ROUTE", raising=False)
    assert S.supply_route_live() is False                          # unrelated tests never touch supply
    monkeypatch.setenv("COLONY_PERTURB_SUPPLY_ROUTE", "live")
    assert S.supply_route_live() is True
    monkeypatch.setenv("COLONY_ARM", "control")
    assert S.supply_route_live() is False


def test_route_to_supply_calls_slot_refill_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "PERTURB_SUPPLY_LOG", tmp_path / "perturb_supply_route.jsonl")
    calls = []

    class Sup:
        def slot_refill(self, cid):
            calls.append(cid)
            return {"open": 0, "pages_read": 12, "requests": 20, "new": [{"id": "oc_A1_0"}]}
    row = S.route_to_supply("cX", supply=Sup())
    assert calls == ["cX"] and row["new"] == ["oc_A1_0"] and row["authorized"] is False
    rows = [json.loads(x) for x in (tmp_path / "perturb_supply_route.jsonl").read_text().splitlines()]
    assert rows == [row]
