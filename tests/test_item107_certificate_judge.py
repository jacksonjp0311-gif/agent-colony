"""Item 107: certificate proof judge (Gosper certificates, independent re-check, non-routine rule)."""
from colony import certificate_judge as C


def test_gosper_certificate_found_and_verified():
    c = C.find_gosper("Sum_{k=1..n} k*k!")
    assert c and c["type"] == "gosper_sum"
    ok, why = C.verify_gosper(c, "(n+1)! - 1")
    assert ok, why


def test_wrong_closed_form_rejected():
    c = C.find_gosper("Sum_{k=1..n} k*k!")
    ok, why = C.verify_gosper(c, "(n+1)! - 2")
    assert not ok


def test_central_binomial_partial_sum():
    c = C.find_gosper("Sum_{k=0..n} binomial(2k,k)/4^k")
    ok, why = C.verify_gosper(c, "(2n+1)*binomial(2n,n)/4^n")
    assert ok, why


def test_definite_sums_not_handled():
    assert C.find_gosper("Sum_{k=0..n} binomial(n,k)") is None


def test_tampered_certificate_rejected():
    c = C.find_gosper("Sum_{k=1..n} k*k!")
    bad = dict(c, G_text="2*factorial(k)", R_text="2/k")
    ok, _ = C.verify_gosper(bad, "(n+1)! - 1")
    assert not ok


def test_pole_of_R_inside_range_rejected():
    c = C.find_gosper("Sum_{k=0..n} k*k!")       # R = 1/k has a pole at k = 0
    ok, why = C.verify_gosper(c, "(n+1)! - 1")
    assert not ok and "pole" in why


def test_non_routine_rule():
    assert not C.counts_as_non_routine({"certificate_verified": True, "routine": True})
    assert not C.counts_as_non_routine({"certificate_verified": False, "routine": False})
    assert not C.counts_as_non_routine({"routine": False})
    assert C.counts_as_non_routine({"certificate_verified": True, "routine": False})


def test_score_requires_certificate_for_non_routine():
    from colony import oeis_conjectures as OC
    state = {}
    e = {"id": "x", "anum": "A1", "definition": {"kind": "gf"}}
    OC._score(state, e, [{"status": "proved_checked", "checker": "holonomic closure, order 3"}])
    p = state["scoreboard"]["proofs"]["x"]
    assert p["routine"] is False and p["certificate_verified"] is False
    from colony import twin
    assert twin.non_routine_count({"x": p}) == 0
    p2 = dict(p, certificate_verified=True)
    assert twin.non_routine_count({"x": p2}) == 1


def test_off_on_control(monkeypatch):
    from colony import arm
    monkeypatch.setattr(arm, "is_control", lambda: True)
    assert C.enabled() is False
