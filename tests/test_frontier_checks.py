"""COLONY_FRONTIER=live: surviving self-chosen conjectures become authored checks (Oracle judges)."""
from __future__ import annotations

import ast

import colony.authoring as A
import colony.frontier_checks as FK

REG = {
    "a": {"kind": "divides", "lhs": "sigma", "rhs": "dbl((sigma*sqfree))", "params": {}, "unknown": True,
          "sig": "f0461a58aa", "hunt_value": 1.0, "statement": "sigma(n) divides dbl((sigma*sqfree))(n) for all n >= 1",
          "label": "conjecture surviving 59970 checks", "found_at": "t1"},
    "b": {"kind": "le", "lhs": "phi", "rhs": "n", "params": {}, "unknown": False, "sig": "11111111aa",
          "hunt_value": 0.0, "statement": "x", "label": "y", "found_at": "t0"},
    "c": {"kind": "le", "lhs": "pi", "rhs": "(one+tau)", "params": {}, "unknown": True, "falsified_later": True,
          "sig": "22222222aa", "hunt_value": 1.0, "statement": "z", "label": "falsified on re-test", "found_at": "t2"},
}


def test_candidates_only_live_surprises_not_yet_authored():
    c = FK.candidates(set(), state={"registry": REG})
    assert [x["name"] for x in c] == ["authored_frontier_divides_xf0461a58_w1"]
    assert FK.candidates({"authored_frontier_divides_xf0461a58_w1"}, state={"registry": REG}) == []
    ast.parse(c[0]["fn_src"])
    assert "__import__" not in c[0]["fn_src"] and "not proof" in c[0]["fn_src"]


def test_built_check_passes_the_authoring_guards():
    from colony.conjecture_desk import LEMMA_IMPL
    src = LEMMA_IMPL.read_text(encoding="utf-8")
    marker = A.INSERT_MARKER if A.INSERT_MARKER in src else A.FALLBACK_MARKER
    src = FK.ensure_bridges(src, marker)
    cand = FK.candidates(set(), state={"registry": REG})[0]
    new_src = A.insert_disabled(src, cand["name"], cand["fn_src"])
    res = A.verify_candidate(new_src, cand["name"], cand["verify_fns"])
    assert res["accepted"], res
    assert res["falsifiable"]["frontier_holds"] and res["counts"]["frontier_holds"] >= 3


def test_authoring_uses_frontier_candidates_only_when_live(monkeypatch):
    calls = []
    monkeypatch.setattr(FK, "candidates", lambda names, **k: calls.append(1) or [])
    monkeypatch.setattr(FK, "pending", lambda src: [])
    monkeypatch.setattr(A, "MAX_AUTHORED_TOTAL", 10 ** 6)   # independent of how many checks main holds
    monkeypatch.setenv("COLONY_FRONTIER", "shadow")
    A.author_checks(write=False, cycle_id="t")
    assert calls == []
    monkeypatch.setenv("COLONY_FRONTIER", "live")
    A.author_checks(write=False, cycle_id="t")
    assert calls == [1]


def test_old_registry_rewrites_are_rescreened():
    old = {"kind": "cong", "lhs": "D((digsum+lpf))", "rhs": "", "params": {"m": 2, "r": 0, "q": 2, "s": 0},
           "unknown": True, "sig": "33333333aa", "hunt_value": 1.0, "statement": "s", "label": "l", "found_at": "t"}
    assert not FK.still_new(old)
    assert FK.still_new(REG["a"])
