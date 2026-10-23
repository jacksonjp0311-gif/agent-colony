"""Compositional triviality check (colony/compositional.py) and open-target incentives."""
import random

import pytest

from colony import compositional as CP
from colony import frontier_conjectures as FC


@pytest.fixture(scope="module")
def T():
    return FC.Tables(lim=FC.BRIDGE_LIM, exp_n=FC.BRIDGE_EXP)


def _c(lhs, **params):
    return {"kind": "cong", "params": params, "_le": FC.parse(lhs), "_re": None}


def test_automata_match_tables(T):
    for w in CP.WORDS:
        assert CP.word_ok(w, T), w


def test_baum_never_one_at_2_mod_3():
    assert CP.reachable("baum", 3)[2] == frozenset({0})
    assert CP.reachable("baum", 3)[1] == frozenset({0, 1})


def test_regression_da29c2e70c3c733b_is_known_in_principle(T):
    ex = CP.explain(_c("dbl(gcd(baum,oxa072856))", m=2, q=3, r=0, s=1), T)
    assert ex and ex["label"] == "known_in_principle(component_facts)"
    assert ex["word_constants"]["1"] == {"dbl(baum)": 0}
    assert any("period 9" in f for f in ex["facts"])


def test_false_variant_not_explained(T):
    # n = 0 (mod 3): baum(2n) varies, A072856(2n) is odd at some of them -> not implied
    assert CP.explain(_c("dbl(gcd(baum,oxa072856))", m=2, q=3, r=0, s=0), T) is None


def test_trivial_reason_live_only(T, monkeypatch):
    c = _c("dbl(gcd(baum,oxa072856))", m=2, q=3, r=0, s=1)
    monkeypatch.setenv("COLONY_COMPOSITIONAL", "live")
    assert FC.trivial_reason(c, T, random.Random(1), FC.fit_n()) != ""
    monkeypatch.setenv("COLONY_COMPOSITIONAL", "shadow")
    assert CP.mode() == "shadow"


def test_surprise_credit_zero_when_implied(monkeypatch):
    from colony import surprise_credit as SC
    r = {"kind": "cong", "lhs": "dbl(gcd(baum,oxa072856))", "rhs": "", "params": {"m": 2, "q": 3, "r": 0, "s": 1},
         "unknown": True, "known_check": "no known result found", "reference": "no reference found",
         "prediction": 0.4, "range": [13, 200], "sig": "da29c2e70c3c733b"}
    monkeypatch.setenv("COLONY_COMPOSITIONAL", "live")
    assert SC.compositional(r).startswith("known in principle")
    assert SC.credit(r, trivial=False)["credit"] == 0.0
    monkeypatch.setenv("COLONY_COMPOSITIONAL", "off")
    assert SC.compositional(r) == ""


def test_berlekamp_massey_period():
    fib2 = [0, 1]
    for _ in range(400):
        fib2.append((fib2[-1] + fib2[-2]) % 2)
    f = CP._bm_period(fib2[1:], 2)
    assert f and f["P"] == 3


def test_open_target_weight(monkeypatch):
    from colony import open_targets as OT
    monkeypatch.setattr(OT, "TARGET", {"oxa999999": "conjecture_formula"})
    r = {"lhs": "D(oxa999999)", "rhs": ""}
    monkeypatch.setenv("COLONY_OPEN_TARGETS", "off")
    assert OT.credit_weight(r) == 1.0
    monkeypatch.setenv("COLONY_OPEN_TARGETS", "live")
    assert OT.credit_weight(r) == OT.OPEN_CREDIT
    assert OT.credit_weight({"lhs": "D(oxa072856)"}) == 1.0
