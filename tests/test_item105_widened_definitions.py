"""Item 105: widened OEIS definitions (NAME / FORMULA / guess), accepted only on a full b-file match."""
import math

import pytest

from colony import oeis_conjectures as OC
from colony import oeis_definitions as OD


def _cat(n):
    return math.comb(2 * n, n) // (n + 1)


def test_parse_sum_binomial_factorial_and_implicit_mult():
    t = OD.parse_expr("Sum_{k=0..n} (-1)^k*binomial(n,k)*k! + 2n(n+1)")
    assert t[0] == "add" and t[1][0] == "sum"
    v = OD.eval_a(t, {"n": 3}, lambda i: 0, 1e18)
    assert v == sum((-1) ** k * math.comb(3, k) * math.factorial(k) for k in range(4)) + 24
    assert OD.eval_b(t, {"n": 3}, lambda i: 0, 1e18) == (int(v), 1)


def test_unknown_names_and_double_factorial_rejected():
    for bad in ("a(n) = Q(n)+1", "a(n) = n!!", "a(n) = Sum_{d|n} d"):
        assert OD._xexpr_from(bad) is None


def test_name_recursion_with_stated_initial_value_reproduces():
    d = OD._xexpr_from("a(n) = n*a(n-1) + 1, a(0) = 0.")
    assert d and d["init"] == {"0": 0}
    terms = [0]
    for n in range(1, 60):
        terms.append(n * terms[-1] + 1)
    ok, why = OD.reproduces(d, 0, terms)
    assert ok, why
    bad = list(terms)
    bad[40] += 1
    assert not OD.reproduces(d, 0, bad)[0]


def test_floor_and_catalan_alias_both_paths():
    d = OD._xexpr_from("a(n) = 3*Catalan(n) - Catalan(n-1) - 1.")
    terms = [3 * _cat(n) - _cat(n - 1) - 1 for n in range(1, 80)]
    assert OD.reproduces(d, 1, terms)[0]
    d2 = OD._xexpr_from("a(n) = binomial(n,floor(n/2))*(n+1)!.")
    t2 = [math.comb(n, n // 2) * math.factorial(n + 1) for n in range(0, 60)]
    assert OD.reproduces(d2, 0, t2)[0]


def test_holonomic_from_formula_line():
    d = OD._holo_from("D-finite with recurrence (n+1)*a(n) +2*(-2*n+1)*a(n-1) = 0. - _R. J. Mathar_, Jan 01 2020")
    assert d and d["polys"] == {"0": [1, 1], "1": [2, -4]}
    terms = [_cat(n) for n in range(0, 120)]
    assert OD.reproduces(d, 0, terms)[0]


def test_inhomogeneous_or_nonpolynomial_recurrence_rejected():
    assert OD._holo_from("a(n) = 2*a(n-1) + 1") is None
    assert OD._holo_from("a(n) = 2^n*a(n-1)") is None


def test_conjectural_formula_lines_never_used():
    e = {"anum": "A999999", "name": "Something combinatorial.", "text": "Conjecture: a(n) = 2*a(n-1).",
         "offset": 0, "terms": [2 ** n for n in range(60)], "claim": {"form": "relation", "parts": ["a(n)", "2*a(n-1)"]}}
    cache = {"entries": {"A999999": {"formula": [
        "Conjecture: a(n) = 2^n. - _X_, 2020",
        "a(n) = 2^n (empirical).",
        "a(n) = 2*a(n-1). - _Y_",      # the claim itself
        "a(n) = 2^n. - _Z_, 2001",
    ]}}}
    cands = OD.candidates(e, cache)
    assert [c["source"] for c in cands] == ["a(n) = 2^n"]
    d, tried = OD.find_definition(e, cache)
    assert d and d["provenance"] == OD.PROV_FORMULA and d["sound"] is False
    assert any("circular" in t["why"] for t in tried)


def test_guess_used_only_for_non_circular_claims():
    terms = [_cat(n) for n in range(0, 200)]
    e = {"anum": "A000000", "name": "Mystery.", "text": "Conjecture: all terms are positive.", "offset": 0,
         "terms": terms, "claim": {"form": "property", "prop": "positive"}}
    d, _ = OD.find_definition(e, {"entries": {}})
    assert d and d["provenance"] == OD.PROV_GUESS and d["kind"] == "holo"
    e2 = dict(e, claim={"form": "relation", "parts": ["(n+1)*a(n)", "2*(2*n-1)*a(n-1)"]},
              text="Conjecture: (n+1)*a(n) = 2*(2*n-1)*a(n-1).")
    d2, tried = OD.find_definition(e2, {"entries": {}})
    assert d2 is None and "circular" in tried[-1]["why"]


def test_extend_past_bfile_and_label_conditional(monkeypatch):
    monkeypatch.setenv("COLONY_OEIS_DEF_WIDEN", "live")
    d = OD._holo_from("D-finite with recurrence (n+1)*a(n) +2*(-2*n+1)*a(n-1) = 0")
    d["provenance"] = OD.PROV_FORMULA
    terms = [_cat(n) for n in range(0, 60)]
    out = OC.extend(d, 0, terms, 200, "A")
    assert out[:200] == [_cat(n) for n in range(200)]
    outB = OC.extend(d, 0, terms, 200, "B")
    assert outB == out
    res = OD.label_result(d, {"status": "counterexample_verified"})
    assert res["status"] == "counterexample_conditional" and res["conditional"]
    assert OC.credit_of({"action": "attempt_disprove", "status": "holds_on_range", "conditional": True,
                         "range": [0, 10 ** 6], "bfile_hi": 59}, 59) == 0.0
    d["provenance"] = OD.PROV_NAME
    assert OD.label_result(d, {"status": "counterexample_verified"})["status"] == "counterexample_verified"


def test_score_keeps_conditional_apart():
    state = {}
    e = {"id": "x", "anum": "A1"}
    OC._score(state, e, [{"action": "attempt_disprove", "status": "holds_on_range", "conditional": True,
                          "range": [0, 500], "bfile_hi": 100, "definition_provenance": "guessed"}])
    sb = state["scoreboard"]
    assert sb["extensions"] == {} and sb["conditional_extensions"]["x"]["to"] == 500


def test_off_on_control(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    from colony import arm
    monkeypatch.setattr(arm, "is_control", lambda: True)
    assert OD.enabled() is False
    assert OD.definition_for({"id": "oc_A002627_0", "offset": 0, "terms": []}) is None


def test_switch_off(monkeypatch):
    monkeypatch.setenv("COLONY_OEIS_DEF_WIDEN", "off")
    assert OD.enabled() is False


def test_no_program_lines_in_cache_reader():
    src = open(OD.__file__).read()
    import re
    assert not re.search(r"(?<![A-Za-z_.])(exec|eval)\(", src)
    assert "import subprocess" not in src


def test_guess_does_not_reopen_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("COLONY_OEIS_DEF_WIDEN", "live")
    monkeypatch.delenv("COLONY_OEIS_DEF_GUESS", raising=False)
    e = {"id": "g1", "offset": 0, "terms": [1, 2, 3]}
    table = {"entries": {"g1": {"terms_sha": OD.terms_sha(e), "definition": {"kind": "holo", "provenance": "guessed",
                                                                            "polys": {"0": [1], "1": [-1]}}}}}
    monkeypatch.setitem(OD._MEMO, "table", table)
    assert OD.definition_for(e) is None
    monkeypatch.setenv("COLONY_OEIS_DEF_GUESS", "live")
    assert OD.definition_for(e)["provenance"] == "guessed"
