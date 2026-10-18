"""colony.new_data: computing past the published OEIS frontier, verified two ways (offline fixtures)."""
from __future__ import annotations

import json

import pytest

from colony import new_data as N
from colony import newdata_checks as K


class FakeNet:
    def __init__(self, files):
        self.files, self.n = files, 0

    def get(self, url, name):
        self.n += 1
        return self.files.get(name)


def _bfile(vals, k0=1):
    return "".join(f"{k0 + i} {v}\n" for i, v in enumerate(vals))


@pytest.fixture()
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "ROOT", tmp_path)
    monkeypatch.setattr(N, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(N, "INDEX", tmp_path / "f" / "index.json")
    monkeypatch.setattr(N, "CLAIMS", tmp_path / "f" / "claims.json")
    monkeypatch.setattr(N, "LEDGER", tmp_path / "f" / "NEW_DATA.md")
    monkeypatch.setattr(N, "DATA_DIR", tmp_path / "f" / "data")
    monkeypatch.setenv("COLONY_NEWDATA", "shadow")
    return tmp_path


def _files(anum, vals, links=()):
    num = anum[1:]
    return {f"b{num}.txt": _bfile(vals), f"{anum}.json": json.dumps([{"name": "test seq", "link": list(links)}])}


def test_methods_agree_and_mode_default(monkeypatch):
    monkeypatch.delenv("COLONY_NEWDATA", raising=False)
    assert N.mode() == "shadow"
    assert K.self_test(force=True)["ok"]


def test_beyond_frontier_verified_two_ways_and_ledger(tmp_state, monkeypatch):
    monkeypatch.setattr(N, "items", lambda: ["col_steps:terms", "col_odd:terms"])
    pub = N.MENU["col_steps"]["a"](300)
    net = FakeNet(_files("A006577", pub))
    lookup = lambda seq: {"status": "found", "anums": ["A006577"]}  # noqa: E731
    s = N.run_cycle("c1", net=net, lookup=lookup)
    # discovery ran; the matched entry is pushed past k = 300
    idx = json.loads(N.INDEX.read_text())
    assert "A006577" in idx["entries"]
    for _ in range(3):
        s = N.run_cycle("c2", net=net, lookup=lookup)
    claims = json.loads(N.CLAIMS.read_text())["claims"]
    c = next(c for c in claims if c["anum"] == "A006577")
    assert c["label"] == N.LABEL_NEW and c["k_range"][0] == 301
    rows = [tuple(map(int, l.split())) for l in (tmp_state / c["data_file"]).read_text().splitlines() if l[0] != "#"]
    full = N.MENU["col_steps"]["b"]([k for k, _ in rows])
    assert [v for _, v in rows] == full
    assert "A006577" in N.LEDGER.read_text()
    # the authored check recomputes by method B and is falsifiable
    b = K.build(c)
    assert b and "newdata_term('col_steps'" in b["expr"]
    ns = {"newdata_term": lambda key, n: int(N.MENU[key]["b"]([n])[0])}
    assert eval(b["expr"], ns)
    assert not eval(b["expr"], {"newdata_term": lambda key, n: False})


def test_mismatch_and_unknown_never_claim(tmp_state):
    pub = N.MENU["col_steps"]["a"](300)
    pub[200] += 1                                  # published data differ from method A
    net = FakeNet(_files("A006577", pub))
    e = N.discover("col_steps:terms", net, lambda seq: {"status": "found", "anums": ["A006577"]})
    assert e["status"] == "matched"
    r = N.push(e, 10.0, net)
    assert r["status"] == "mismatch"
    e2 = N.discover("col_steps:terms", FakeNet({}), lambda seq: {"status": "found", "anums": ["A006577"]})
    assert e2["status"] == N.LABEL_UNKNOWN
    assert N.discover("col_steps:terms", FakeNet({}), None)["status"] == N.LABEL_UNKNOWN


def test_linked_tables_raise_the_frontier(tmp_state):
    pub = N.MENU["col_steps"]["a"](300)
    net = FakeNet(_files("A006577", pub, links=["X, Table of n, a(n) for n = 1..600"]))
    e = N.discover("col_steps:terms", net, lambda seq: {"status": "found", "anums": ["A006577"]})
    r = N.push(e, 10.0, net)
    assert r["status"] == N.LABEL_NEW and r["ns"][0] == 601     # never claims terms a linked table covers
    assert N._linked_extent(["Table of n, a(n) for n = 0..10^6"]) == 10 ** 6


def test_records_beyond_published(tmp_state):
    base = N.MENU["col_steps"]["a"](3000)
    pos, _ = N.records(base)
    net = FakeNet(_files("A006877", pos[:20]))
    e = N.discover("col_steps:recpos", net, lambda seq: {"status": "found", "anums": ["A006877"]})
    assert e["status"] == "matched"
    r = N.push(e, 15.0, net)
    assert r["status"] == N.LABEL_NEW and r["values"][0] == pos[20]
