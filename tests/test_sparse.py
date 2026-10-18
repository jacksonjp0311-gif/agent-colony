"""colony.sparse (Stage 1b): sparse OEIS targets identified by recomputing every published term."""
from __future__ import annotations

import json

import numpy as np
import pytest

from colony import new_data as N
from colony import newdata_checks as K
from colony import sparse as S
from colony import sparse_engine as E


class FakeNet:
    def __init__(self, files):
        self.files, self.n = files, 0

    def get(self, url, name):
        if name in self.files:
            return self.files[name]
        return None


@pytest.fixture()
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "ROOT", tmp_path)
    monkeypatch.setattr(N, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(N, "INDEX", tmp_path / "f" / "index.json")
    monkeypatch.setattr(N, "CLAIMS", tmp_path / "f" / "claims.json")
    monkeypatch.setattr(N, "LEDGER", tmp_path / "f" / "NEW_DATA.md")
    monkeypatch.setattr(N, "DATA_DIR", tmp_path / "f" / "data")
    monkeypatch.setattr(N, "FRONTIER_DIR", tmp_path / "f")
    return tmp_path


def _cand(anum, name, data, offset=1, kw="nonn,more", links=()):
    return {"number": int(anum[1:]), "name": name, "data": ",".join(map(str, data)), "offset": f"{offset},1",
            "keyword": kw, "link": list(links), "comment": []}


def test_engine_two_methods_agree_and_flags(monkeypatch):
    assert S.self_test()["ok"]
    monkeypatch.delenv("COLONY_NEWDATA_SPARSE", raising=False)
    monkeypatch.delenv("COLONY_NEWDATA_DEEP", raising=False)
    assert S.mode() == "shadow" and S.deep_mode() == "shadow"
    # extending a 10,000-term b-file earns ~1/200 of extending a 30-term data section
    assert S.short_weight(10000) < S.short_weight(30) / 100


def test_eligibility_short_frontier_only():
    ok = S._parse_candidate(_cand("A352229", "Numbers that can be expressed as the sum of two primes in exactly 7 ways.",
                                  [78, 96, 112, 130, 140, 176]))
    assert S.eligible(ok) is None
    long_ = S._parse_candidate(_cand("A000001", "Goldbach partitions", list(range(1, 10)),
                                     links=["N. J. A. Sloane, <a href=\"/A000001/b000001.txt\">Table of n, a(n) for n = 1..10000</a>"]))
    assert "long frontier" in S.eligible(long_)
    assert S.eligible(S._parse_candidate(_cand("A000002", "Goldbach x", [1, 2, 3, 4, 5, 6], kw="nonn"))) is not None


def test_low_variety_list_matches_by_full_recomputation_and_extends(tmp_state):
    """A 'numbers with exactly c Goldbach partitions' list: low variety, found by recomputing all terms."""
    v = E.ITEMS["gb_prime_m"]["a"](3000)
    full = E.listing("eq7", v)
    pub = full[:6]                              # pretend the OEIS lists only the first six
    c = S._parse_candidate(_cand("A999001", "Numbers that can be expressed as the sum of two primes in exactly 7 ways.", pub))
    rows, _src = S.published_rows(c, FakeNet({}))
    m = S.match(c, rows, 30)
    assert m["status"] == "matched" and any(h["item"] == "gb_prime_m" and h["op"] == "eq7" for h in m["hits"])
    e = {k: c[k] for k in ("anum", "name", "keywords", "offset", "n_pub", "comment_hint")} | {
        "rows": [list(r) for r in rows], "source": "test", "hits": [h for h in m["hits"] if h["item"] == "gb_prime_m"],
        "checked": "2026-10-18T00:00:00Z", "stats": {"tries": 0, "beyond": 0, "cpu_s": 0.0}}
    r = S.push(e, 30)
    assert r["status"] == S.LABEL_NEW
    assert [v for _, v in r["values"]] == [k for k in full[6:] if k <= r["searched_to"]]
    claims = {"claims": []}
    S.record_claim(claims, e, r, "t", False)
    cl = claims["claims"][0]
    assert cl["kind"] == "sparse" and cl["first"] == [7, full[6]]
    # the authored check recomputes f(k) by method B; it is falsifiable
    b = K.build(cl)
    assert b and "newdata_point('gb_prime_m'" in b["expr"]
    env = {"newdata_point": S.point_b}
    assert eval(b["expr"], env) is True
    bad = b["expr"].replace(f"[{full[6]}, 7]", f"[{full[6]}, 8]")
    assert bad != b["expr"] and eval(bad, env) is False


def test_mismatch_and_ambiguity_never_claim(tmp_state, monkeypatch):
    base = np.arange(1, 5001) % 7
    monkeypatch.setitem(E.ITEMS, "fake_a", {"family": "collatz", "what": "x", "a": lambda N: base[:N],
                                            "b": lambda N: base[:N], "bp": lambda k: int(base[k - 1]), "methods": ["a", "b"]})
    other = base.copy()
    other[100:] = (other[100:] + 1) % 7
    monkeypatch.setitem(E.ITEMS, "fake_b", {"family": "collatz", "what": "y", "a": lambda N: other[:N],
                                            "b": lambda N: other[:N], "bp": lambda k: int(other[k - 1]), "methods": ["a", "b"]})
    rows = [(n, int(base[n - 1])) for n in range(1, 40)]
    e = {"anum": "A999002", "rows": [list(r) for r in rows], "hits": [
        {"item": "fake_a", "op": "terms", "d": 0, "N": 42}, {"item": "fake_b", "op": "terms", "d": 0, "N": 42}],
        "source": "test", "checked": "x", "n_pub": 39}
    assert S.push(e, 5)["status"] == "ambiguous definition"
    # B disagreeing -> unverified, nothing claimed
    monkeypatch.setitem(E.ITEMS, "fake_c", {"family": "collatz", "what": "z", "a": lambda N: base[:N],
                                            "b": lambda N: other[:N], "bp": lambda k: 0, "methods": ["a", "b"]})
    e["hits"] = [{"item": "fake_c", "op": "terms", "d": 0, "N": 42}]
    assert S.push(e, 5)["status"] == "unverified"
    # A no longer reproducing the published terms -> mismatch
    e["rows"][3] = [4, 99]
    assert S.push(e, 5)["status"] == "mismatch"


def test_search_cycle_queues_and_ledger(tmp_state):
    v = E.ITEMS["gb_prime_m"]["a"](3000)
    pub = E.listing("eq8", v)[:7]
    page = json.dumps([_cand("A999003", "Numbers that can be expressed as the sum of two primes in exactly 8 ways.", pub)])
    files = {}
    for q in S.SEARCH_QUERIES[:1]:
        import hashlib
        files["osearch_" + hashlib.sha1(f"{q}|0".encode()).hexdigest()[:16] + ".json"] = page
    net = FakeNet(files)
    st, idx, claims = {}, {"entries": {}}, {"claims": []}
    res = S.run("c1", net, st, idx, claims, 30)
    assert "A999003" in idx["sparse"] and res["pushed"]
    N.write_ledger(claims, idx)
    txt = N.LEDGER.read_text()
    assert "Sparse entries" in txt and "A999003" in txt


def test_authoring_slot_cap_and_one_per_sequence(tmp_state, monkeypatch):
    assert K.slot_allows()
    K.note_slot("newdata")
    assert not K.slot_allows()
    K.note_slot("frontier")
    assert not K.slot_allows()
    K.note_slot("compose")
    assert K.slot_allows()
    claims = {"claims": [
        {"anum": "A006577", "k_range": [10001, 11000], "op": "terms", "label": S.LABEL_NEW, "item": "col_steps:terms"},
        {"anum": "A006577", "k_range": [11001, 12000], "op": "terms", "label": S.LABEL_NEW, "item": "col_steps:terms"}]}
    N._save(N.CLAIMS, claims)
    monkeypatch.setattr(K, "build", lambda c: {"name": K.check_name(c)})
    assert K.candidates({"authored_newdata_a006577_k10001_w1"}) == []
    assert len(K.candidates(set())) == 1
